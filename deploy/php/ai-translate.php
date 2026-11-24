<?php
declare(strict_types=1);

/**
 * BloodMoon AI Bridge — dedicated Azure Translator gateway.
 *
 * Install as /var/www/BloodMoon/translator/ai-translate.php.
 * The existing translate.php (in-world HUDs) and web-translate.php
 * (site translations) are deliberately NOT modified.
 *
 * POST JSON: {"from":"auto","to":"fr","text":"How do I get a free plot?"}
 * Header: X-BloodMoon-Token: <server-side token>
 * Reply: {"ok":true,"from":"en","to":"fr","translatedText":"..."}
 *
 * "auto" omits the Azure &from= parameter, enabling Azure's own language
 * detection. Existing /etc/bloodmoon-translator/config.php is reused.
 */
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function bmAiReply(int $status, array $data): never
{
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    bmAiReply(405, ['ok' => false, 'error' => 'Method not allowed']);
}

$configFile = '/etc/bloodmoon-translator/config.php';
if (!is_file($configFile) || !is_readable($configFile)) {
    bmAiReply(503, ['ok' => false, 'error' => 'Translator configuration unavailable']);
}
$config = require $configFile;
if (!is_array($config)) {
    bmAiReply(503, ['ok' => false, 'error' => 'Translator configuration unavailable']);
}

// A separate token is supported without changing the existing translators.
// If not configured, use the same protected translator token.
$expectedToken = trim((string)($config['ai_api_token'] ?? $config['api_token'] ?? ''));
$suppliedToken = (string)($_SERVER['HTTP_X_BLOODMOON_TOKEN'] ?? '');
if ($expectedToken === '' || $suppliedToken === '' || !hash_equals($expectedToken, $suppliedToken)) {
    bmAiReply(403, ['ok' => false, 'error' => 'Forbidden']);
}

// Bound the request to a single short in-world question.
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 6000) {
    bmAiReply(413, ['ok' => false, 'error' => 'Request too large']);
}
$raw = file_get_contents('php://input', false, null, 0, 6001);
if (!is_string($raw) || strlen($raw) > 6000) {
    bmAiReply(413, ['ok' => false, 'error' => 'Request too large']);
}
$data = json_decode($raw, true);
if (!is_array($data)) {
    bmAiReply(400, ['ok' => false, 'error' => 'Invalid JSON']);
}
$from = trim((string)($data['from'] ?? 'auto'));
$to = trim((string)($data['to'] ?? 'fr'));
$text = trim((string)($data['text'] ?? ''));
$codePattern = '/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$/';
if ($text === '' || strlen($text) > 4000 ||
    ($from !== 'auto' && preg_match($codePattern, $from) !== 1) ||
    preg_match($codePattern, $to) !== 1) {
    bmAiReply(400, ['ok' => false, 'error' => 'Invalid translation request']);
}
// This gateway serves the bot's knowledge search, not arbitrary translation.
if ($to !== 'fr') {
    bmAiReply(400, ['ok' => false, 'error' => 'Unsupported target language']);
}

$key = trim((string)($config['azure_key'] ?? ''));
$base = rtrim((string)($config['azure_endpoint'] ?? 'https://api.cognitive.microsofttranslator.com'), '/');
$region = trim((string)($config['azure_region'] ?? 'global'));
if ($key === '' || !str_starts_with($base, 'https://')) {
    bmAiReply(503, ['ok' => false, 'error' => 'Azure configuration unavailable']);
}
$url = $base . '/translate?api-version=3.0&to=' . rawurlencode($to);
if ($from !== 'auto') {
    $url .= '&from=' . rawurlencode($from);
}
$azureBody = json_encode([['Text' => $text]], JSON_UNESCAPED_UNICODE);
if ($azureBody === false) {
    bmAiReply(400, ['ok' => false, 'error' => 'Invalid UTF-8']);
}
$headers = [
    'Ocp-Apim-Subscription-Key: ' . $key,
    'Content-Type: application/json; charset=utf-8',
];
if ($region !== '' && strcasecmp($region, 'global') !== 0) {
    $headers[] = 'Ocp-Apim-Subscription-Region: ' . $region;
}
$curl = curl_init($url);
if ($curl === false) {
    bmAiReply(502, ['ok' => false, 'error' => 'Translator unavailable']);
}
curl_setopt_array($curl, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => $azureBody,
    CURLOPT_HTTPHEADER => $headers,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CONNECTTIMEOUT => 3,
    CURLOPT_TIMEOUT => 8,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_MAXREDIRS => 0,
]);
$response = curl_exec($curl);
$status = (int)curl_getinfo($curl, CURLINFO_HTTP_CODE);
curl_close($curl);
if (!is_string($response) || $status !== 200 || strlen($response) > 20000) {
    // No resident text, tokens or Azure response bodies in logs or output.
    bmAiReply(502, ['ok' => false, 'error' => 'Azure translation failed']);
}
$azure = json_decode($response, true);
$translated = $azure[0]['translations'][0]['text'] ?? null;
$detected = $azure[0]['detectedLanguage']['language'] ?? null;
if (!is_string($translated) || trim($translated) === '') {
    bmAiReply(502, ['ok' => false, 'error' => 'Invalid Azure translation']);
}
$sourceLanguage = $from === 'auto' && is_string($detected) ? $detected : $from;
bmAiReply(200, [
    'ok' => true,
    'from' => $sourceLanguage,
    'to' => $to,
    'translatedText' => $translated,
]);
