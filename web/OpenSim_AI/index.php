<?php
declare(strict_types=1);

// OpenSim AI Bridge administration. HTTPS and the private configuration are mandatory.
const PRIVATE_CONFIG = '/etc/opensim-ai-bridge/web-admin.php';
const CONTROL_SOCKET = '/run/opensim-ai-bridge-control/control.sock';
const IDLE_SECONDS = 1800;

function esc(string $text): string {
    return htmlspecialchars($text, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
function is_https(): bool {
    return (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (isset($_SERVER['SERVER_PORT']) && (int) $_SERVER['SERVER_PORT'] === 443);
}
if (!is_https()) {
    http_response_code(403);
    exit('HTTPS requis / HTTPS required');
}
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: no-referrer');
// Allow only this page's dedicated model-selector script; keep other inline scripts blocked.
$scriptNonce = base64_encode(random_bytes(18));
header("Content-Security-Policy: default-src 'none'; script-src 'nonce-" . $scriptNonce . "'; style-src 'self' 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");

if (!is_file(PRIVATE_CONFIG) || !is_readable(PRIVATE_CONFIG)) {
    http_response_code(503);
    exit('Administration non configurée (fichier privé manquant).');
}
$config = require PRIVATE_CONFIG;
if (!is_array($config) || !is_string($config['password_hash'] ?? null)
    || strlen($config['password_hash']) < 50) {
    http_response_code(503);
    exit('Configuration administrateur invalide.');
}

ini_set('session.use_strict_mode', '1');
ini_set('session.use_only_cookies', '1');
session_name('OSAI_ADMIN');
session_set_cookie_params([
    'lifetime' => 0,
    'path' => '/OpenSim_AI/',
    'secure' => true,
    'httponly' => true,
    'samesite' => 'Strict',
]);
session_start();

function csrf_token(): string {
    if (!is_string($_SESSION['csrf'] ?? null)) {
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf'];
}
function check_csrf(): bool {
    return isset($_POST['csrf']) && is_string($_POST['csrf'])
        && hash_equals(csrf_token(), $_POST['csrf']);
}
function request_control(string $action, bool $confirm = false, ?array $settings = null, string $botId = 'main', ?array $credentials = null, ?string $expectedName = null): array {
    $errno = 0;
    $errstr = '';
    $fp = @stream_socket_client('unix://' . CONTROL_SOCKET, $errno, $errstr, 2.0);
    if ($fp === false) {
        return ['ok' => false, 'error' => 'Contrôleur local indisponible'];
    }
    stream_set_timeout($fp, 35);
    $payload = ['action' => $action, 'confirm' => $confirm];
    if ($settings !== null) $payload['settings'] = $settings;
    $payload['botId'] = $botId;
    if ($credentials !== null) $payload['credentials'] = $credentials;
    if ($expectedName !== null) $payload['expectedName'] = $expectedName;
    $sent = fwrite($fp, json_encode($payload, JSON_THROW_ON_ERROR) . "\n");
    if ($sent === false) {
        fclose($fp);
        return ['ok' => false, 'error' => 'Erreur de communication avec le contrôleur'];
    }
    $reply = fgets($fp, 4096);
    fclose($fp);
    if (!is_string($reply)) {
        return ['ok' => false, 'error' => 'Le contrôleur ne répond pas'];
    }
    $data = json_decode($reply, true);
    return is_array($data) ? $data : ['ok' => false, 'error' => 'Réponse incorrecte'];
}

$requestedBot = is_string($_POST['botId'] ?? null) ? $_POST['botId'] : (is_string($_GET['bot'] ?? null) ? $_GET['bot'] : 'main');
$selectedBot = preg_match('/^(main|[0-9a-f]{16})$/D', $requestedBot) ? $requestedBot : 'main';
$pageRaw = $_POST['page'] ?? $_GET['page'] ?? 'dashboard';
$page = is_string($pageRaw) && in_array($pageRaw, ['dashboard', 'avatars', 'settings', 'maintenance', 'modules', 'knowledge'], true) ? $pageRaw : 'dashboard';
$now = time();
if (isset($_SESSION['last_activity']) && $now - (int) $_SESSION['last_activity'] > IDLE_SECONDS) {
    $_SESSION = [];
    session_regenerate_id(true);
}
$authenticated = ($_SESSION['admin'] ?? false) === true;
$message = '';
$error = '';
// One-use notices: a command acknowledgement must never be mistaken for live state.
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $message = is_string($_SESSION['flash_message'] ?? null) ? $_SESSION['flash_message'] : '';
    $error = is_string($_SESSION['flash_error'] ?? null) ? $_SESSION['flash_error'] : '';
    unset($_SESSION['flash_message'], $_SESSION['flash_error']);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!check_csrf()) {
        http_response_code(403);
        exit('Jeton CSRF incorrect. Recharge la page.');
    }
    $action = is_string($_POST['action'] ?? null) ? $_POST['action'] : '';
    if ($action === 'logout') {
        $_SESSION = [];
        session_regenerate_id(true);
        header('Location: ./');
        exit;
    }
    if (!$authenticated) {
        if ($action === 'login') {
            // Session-level throttling; HTTPS + additional Apache restrictions recommended.
            $failed = (int) ($_SESSION['failed'] ?? 0);
            $lockedUntil = (int) ($_SESSION['lock_until'] ?? 0);
            if ($now < $lockedUntil) {
                $error = 'Trop de tentatives : réessaie plus tard.';
            } else {
                $submitted = is_string($_POST['password'] ?? null) ? $_POST['password'] : '';
                if (password_verify($submitted, $config['password_hash'])) {
                    session_regenerate_id(true);
                    $_SESSION['admin'] = true;
                    $_SESSION['failed'] = 0;
                    $_SESSION['last_activity'] = $now;
                    $authenticated = true;
                    $message = 'Connexion réussie.';
                } else {
                    $_SESSION['failed'] = $failed + 1;
                    if ($_SESSION['failed'] >= 5) {
                        $_SESSION['lock_until'] = $now + 900;
                        $_SESSION['failed'] = 0;
                    }
                    $error = 'Mot de passe incorrect.';
                }
            }
        }
    } else {
        $allowed = ['start', 'stop', 'restart', 'firestorm', 'resume'];
        if ($action === 'vocabulary_upsert' || $action === 'vocabulary_delete') {
            $page = 'knowledge';
            $term = is_string($_POST['term'] ?? null) ? trim($_POST['term']) : '';
            if ($action === 'vocabulary_upsert') {
                $values = [
                    'previous' => is_string($_POST['previous'] ?? null) ? trim($_POST['previous']) : '',
                    'term' => $term,
                    'aliases' => is_string($_POST['aliases'] ?? null) ? trim($_POST['aliases']) : '',
                    'keywords' => is_string($_POST['keywords'] ?? null) ? trim($_POST['keywords']) : '',
                    'domain' => is_string($_POST['domain'] ?? null) ? $_POST['domain'] : ''
                ];
            } else {
                $values = ['term' => $term];
            }
            $response = request_control($action, false, $values, 'main');
            if ($response['ok'] ?? false) {
                $message = $action === 'vocabulary_upsert'
                    ? 'Terme sauvegardé. Il est immédiatement disponible pour les prochaines recherches.'
                    : 'Terme supprimé. La modification est immédiatement disponible.';
            } else {
                $error = (string) ($response['error'] ?? 'Impossible de modifier le vocabulaire.');
            }
        } elseif ($action === 'knowledge_refresh') {
            $page = 'knowledge';
            $response = request_control('knowledge_refresh');
            if ($response['ok'] ?? false) {
                $message = !empty($response['result']['alreadyRunning'])
                    ? 'Une synchronisation documentaire est déjà en cours.'
                    : 'Synchronisation documentaire lancée en tâche indépendante.';
            } else {
                $error = (string) ($response['error'] ?? 'Impossible de démarrer la synchronisation.');
            }
        } elseif ($action === 'knowledge_local_refresh') {
            $page = 'knowledge';
            $response = request_control('knowledge_local_refresh');
            if ($response['ok'] ?? false) {
                $message = !empty($response['result']['alreadyRunning'])
                    ? 'Indexation des fiches TXT déjà en cours.'
                    : 'Réindexation des fiches TXT lancée.';
            } else {
                $error = (string) ($response['error'] ?? 'Impossible de réindexer les fiches TXT.');
            }
        } elseif ($action === 'fleet_stop' || $action === 'fleet_resume') {
            $page = 'maintenance';
            if (($_POST['fleet_confirm'] ?? '') !== 'yes') {
                $error = 'Confirme cette opération globale.';
            } else {
                $response = request_control($action, true);
                if ($response['ok'] ?? false) {
                    $message = $action === 'fleet_stop' ? 'Maintenance générale activée.' : 'Maintenance générale terminée.';
                } else {
                    $error = (string) ($response['error'] ?? 'Erreur de maintenance générale.');
                }
            }
        } elseif ($action === 'delete_bot') {
            $page = 'avatars';
            $expectedName = is_string($_POST['confirm_name'] ?? null) ? trim($_POST['confirm_name']) : '';
            if ($selectedBot === 'main' || ($_POST['delete_confirm'] ?? '') !== 'yes' || $expectedName === '') {
                $error = 'Suppression refusée : confirmation incomplète ou avatar principal.';
            } else {
                $response = request_control('delete_bot', true, null, $selectedBot, null, $expectedName);
                if ($response['ok'] ?? false) {
                    $message = 'Avatar supprimé de OpenSim AI Bridge : ' . $expectedName . '. Son compte sur la grille n’a pas été supprimé.';
                    $selectedBot = 'main';
                } else {
                    $error = (string) ($response['error'] ?? 'Impossible de supprimer cet avatar.');
                }
            }
        } elseif ($action === 'create_bot') {
            $page = 'avatars';
            $coords = [];
            foreach (['x' => 8192, 'y' => 8192, 'z' => 4096] as $axis => $limit) {
                $n = filter_var($_POST[$axis] ?? null, FILTER_VALIDATE_INT,
                    ['options' => ['min_range' => 0, 'max_range' => $limit]]);
                if ($n === false) { $error = 'Coordonnées invalides.'; break; }
                $coords[$axis] = $n;
            }
            if ($error === '') {
                $credentials = [
                    'firstName' => is_string($_POST['firstName'] ?? null) ? trim($_POST['firstName']) : '',
                    'lastName' => is_string($_POST['lastName'] ?? null) ? trim($_POST['lastName']) : '',
                    'password' => is_string($_POST['avatarPassword'] ?? null) ? $_POST['avatarPassword'] : '',
                    'region' => is_string($_POST['newRegion'] ?? null) ? trim($_POST['newRegion']) : '',
                    'x' => $coords['x'], 'y' => $coords['y'], 'z' => $coords['z'],
                ];
                $response = request_control('create_bot', false, null, 'main', $credentials);
                unset($credentials);
                if ($response['ok'] ?? false) {
                    $newId = (string) ($response['result']['botId'] ?? '');
                    if (preg_match('/^[0-9a-f]{16}$/D', $newId)) $selectedBot = $newId;
                    $message = !empty($response['result']['started'])
                        ? 'Avatar enregistré : connexion en cours.'
                        : 'Avatar enregistré, mais le démarrage du service a échoué.';
                } else {
                    $error = (string) ($response['error'] ?? 'Création impossible.');
                }
            }
        } elseif ($action === 'set_avatar_ai_enabled') {
            $page = 'modules';
            $response = request_control('set_avatar_ai_enabled', false,
                ['enabled' => ($_POST['avatarAiEnabled'] ?? '') === '1'], $selectedBot);
            if ($response['ok'] ?? false) {
                $message = 'IA de cet avatar mise à jour. Redémarre cet avatar pour appliquer le changement.';
            } else {
                $error = (string)($response['error'] ?? 'Impossible de modifier le mode IA.');
            }
        } elseif ($action === 'save_multi_ai_settings') {
            $page = 'modules';
            $entries = is_array($_POST['profiles'] ?? null) ? array_values($_POST['profiles']) : [];
            $profiles = [];
            foreach ($entries as $item) {
                if (!is_array($item)) continue;
                $profiles[] = [
                    'id' => is_string($item['id'] ?? null) ? $item['id'] : '',
                    'provider' => is_string($item['provider'] ?? null) ? $item['provider'] : '',
                    'model' => is_string($item['model'] ?? null) ? trim($item['model']) : '',
                    'enabled' => ($item['enabled'] ?? '') === '1',
                    'verified' => false,
                    'apiKey' => is_string($item['apiKey'] ?? null) ? trim($item['apiKey']) : '',
                ];
            }
            $hourly = filter_var($_POST['maxRequestsPerHour'] ?? null, FILTER_VALIDATE_INT,
                ['options' => ['min_range' => 1, 'max_range' => 120]]);
            $cooldown = filter_var($_POST['minSecondsBetweenRequests'] ?? null, FILTER_VALIDATE_INT,
                ['options' => ['min_range' => 5, 'max_range' => 3600]]);
            if ($hourly === false || $cooldown === false) {
                $error = 'Limites IA invalides.';
            } else {
                $settings = [
                    'enabled' => ($_POST['aiEnabled'] ?? '') === '1',
                    'mode' => ($_POST['aiMode'] ?? 'auto') === 'single' ? 'single' : 'auto',
                    'profiles' => $profiles,
                    'maxRequestsPerHour' => $hourly,
                    'minSecondsBetweenRequests' => $cooldown,
                    'systemPrompt' => is_string($_POST['systemPrompt'] ?? null)
                        ? trim($_POST['systemPrompt']) : '',
                ];
                $response = request_control('save_multi_ai_settings', false, $settings, $selectedBot);
                if ($response['ok'] ?? false) {
                    $message = 'Moteurs IA enregistrés. Redémarre cet avatar pour appliquer la configuration.';
                } else {
                    $error = (string) ($response['error'] ?? 'Enregistrement multi-IA refusé.');
                }
            }
        } elseif (str_starts_with($action, 'test_multi_ai_profile:')) {
            $page = 'modules';
            $profileId = substr($action, strlen('test_multi_ai_profile:'));
            if (!preg_match('/^[a-z0-9-]{1,24}$/D', $profileId)) {
                $error = 'Profil de test invalide.';
            } else {
                $response = request_control('test_multi_ai_profile', false, ['id' => $profileId], $selectedBot);
                if ($response['ok'] ?? false) {
                    $message = 'Test du fournisseur réussi ! Profil approuvé. Redémarre cet avatar après activation.';
                } else {
                    $error = (string) ($response['error'] ?? 'Échec du test fournisseur.');
                }
            }
        } elseif ($action === 'save_ai_settings') {
            $page = 'modules';
            $uuidsRaw = is_string($_POST['authorizedUuids'] ?? null) ? $_POST['authorizedUuids'] : '';
            $uuids = array_values(array_filter(array_map('trim', preg_split('/[\\r\\n,;]+/', $uuidsRaw) ?: []), fn($item) => $item !== ''));
            $hourly = filter_var($_POST['maxRequestsPerHour'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 120]]);
            $cooldown = filter_var($_POST['minSecondsBetweenRequests'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 5, 'max_range' => 3600]]);
            if ($hourly === false || $cooldown === false) {
                $error = 'Limites de consommation IA invalides.';
            } else {
                $settings = [
                    'enabled' => ($_POST['aiEnabled'] ?? '') === '1',
                    'provider' => is_string($_POST['aiProvider'] ?? null) ? $_POST['aiProvider'] : '',
                    'model' => is_string($_POST['aiModel'] ?? null) ? trim($_POST['aiModel']) : '',
                    'authorizedUuids' => $uuids,
                    'publicAccess' => ($_POST['aiPublicAccess'] ?? '') === '1',
                    'maxRequestsPerHour' => $hourly,
                    'minSecondsBetweenRequests' => $cooldown,
                    'systemPrompt' => is_string($_POST['systemPrompt'] ?? null) ? trim($_POST['systemPrompt']) : '',
                    'apiKey' => is_string($_POST['aiKey'] ?? null) ? trim($_POST['aiKey']) : '',
                ];
                $response = request_control('save_ai_settings', false, $settings, $selectedBot);
                unset($settings);
                if ($response['ok'] ?? false) {
                    $message = 'Configuration IA sauvegardée pour cet avatar. Redémarre son service pour appliquer les changements.';
                } else {
                    $error = (string) ($response['error'] ?? 'Erreur de configuration IA.');
                }
            }
        } elseif ($action === 'save_settings') {
            $page = 'settings';
            $startMode = is_string($_POST['startMode'] ?? null) ? $_POST['startMode'] : 'region';
            if (!in_array($startMode, ['region', 'last'], true)) {
                $error = 'Mode de démarrage invalide.';
            }
            $region = is_string($_POST['region'] ?? null) ? trim($_POST['region']) : '';
            $coords = [];
            foreach (['x' => 8192, 'y' => 8192, 'z' => 4096] as $axis => $limit) {
                $raw = $_POST[$axis] ?? null;
                $number = filter_var($raw, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0, 'max_range' => $limit]]);
                if ($number === false) {
                    $error = 'Coordonnées invalides.';
                    break;
                }
                $coords[$axis] = $number;
            }
            if ($error === '' && ($region === '' || strlen($region) > 80)) {
                $error = 'Nom de région invalide.';
            }
            if ($error === '') {
                $settings = [
                    'startMode' => $startMode,
                    'region' => $region,
                    'x' => $coords['x'],
                    'y' => $coords['y'],
                    'z' => $coords['z'],
                    'enableIM' => ($_POST['enableIM'] ?? '') === '1',
                    'enableLocalChat' => ($_POST['enableLocalChat'] ?? '') === '1',
                    'reconnectEnabled' => ($_POST['reconnectEnabled'] ?? '') === '1',
                ];
                $response = request_control('save_settings', false, $settings, $selectedBot);
                if ($response['ok'] ?? false) {
                    $message = 'Configuration sauvegardée. Redémarre le bot depuis cette page pour appliquer les changements.';
                } else {
                    $error = (string) ($response['error'] ?? 'Erreur de sauvegarde');
                }
            }
        } elseif (in_array($action, $allowed, true)) {
            $page = 'dashboard';
            if ($action === 'resume' && ($_POST['viewer_closed'] ?? '') !== 'yes') {
                $error = 'Confirme d’abord la fermeture de Firestorm.';
            } else {
                $response = request_control($action, $action === 'resume', null, $selectedBot);
                if ($response['ok'] ?? false) {
                    $message = 'Commande exécutée : ' . $action;
                } else {
                    $error = (string) ($response['error'] ?? 'Erreur du contrôleur');
                }
            }
        } else {
            $error = 'Action non autorisée.';
        }
    }
}
// Post / Redirect / Get: refresh and navigation never resubmit passwords or bot commands.
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $authenticated) {
    if ($message !== '') $_SESSION['flash_message'] = $message;
    if ($error !== '') $_SESSION['flash_error'] = $error;
    if (($_POST['action'] ?? '') === 'create_bot' && $error === '') {
        $page = 'dashboard';
    }
    header('Location: ./?page=' . rawurlencode($page) . '&bot=' . rawurlencode($selectedBot), true, 303);
    exit;
}
if ($authenticated) {
    $_SESSION['last_activity'] = $now;
}
$listResponse = $authenticated ? request_control('list_bots') : null;
$bots = is_array($listResponse['result']['bots'] ?? null) ? $listResponse['result']['bots'] : [];
$knownBots = array_column($bots, 'id');
if (!in_array($selectedBot, $knownBots, true)) $selectedBot = 'main';
$fleetResult = $authenticated ? request_control('fleet_status') : null;
$fleet = is_array($fleetResult['result'] ?? null) ? $fleetResult['result'] : null;
$status = $authenticated ? request_control('status', false, null, $selectedBot) : null;
$state = is_array($status['result'] ?? null) ? $status['result'] : null;
$settingsResult = $authenticated ? request_control('get_settings', false, null, $selectedBot) : null;
$botSettings = is_array($settingsResult['result'] ?? null) ? $settingsResult['result'] : null;
$aiResult = $authenticated && $page === 'modules' ? request_control('get_ai_settings', false, null, $selectedBot) : null;
$aiSettings = is_array($aiResult['result'] ?? null) ? $aiResult['result'] : null;
$multiResult = $authenticated && $page === 'modules' ? request_control('get_multi_ai_settings', false, null, $selectedBot) : null;
$multiSettings = is_array($multiResult['result'] ?? null) ? $multiResult['result'] : null;
$avatarAiResult = $authenticated && $page === 'modules' ? request_control('get_avatar_ai_enabled', false, null, $selectedBot) : null;
$avatarAiEnabled = ($avatarAiResult['result']['enabled'] ?? false) === true;
$vocabularyResponse = $authenticated && $page === 'knowledge' ? request_control('vocabulary_list') : null;
$vocabulary = is_array($vocabularyResponse['result']['entries'] ?? null)
    ? $vocabularyResponse['result']['entries'] : null;
$kbResponse = $authenticated && $page === 'knowledge' ? request_control('knowledge_status') : null;
$kb = is_array($kbResponse['result'] ?? null) ? $kbResponse['result'] : null;
$kbRunning = in_array(($kb['service'] ?? ''), ['active', 'activating', 'reloading'], true);
$selectedName = 'Avatar';
foreach ($bots as $bot) {
    if (($bot['id'] ?? '') === $selectedBot) {
        $selectedName = trim((string) ($bot['firstName'] ?? '') . ' ' . (string) ($bot['lastName'] ?? ''));
        break;
    }
}
?>
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>BloodMoon AI — Administration</title>
<?php if ($authenticated && $page === 'dashboard'): ?>
<!-- Refresh only the read-only dashboard. Never reload an open settings or creation form. -->
<meta http-equiv="refresh" content="10">
<?php endif ?>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#0b1020;color:#e8edf9;line-height:1.5}
main{max-width:940px;margin:3rem auto;padding:0 1.2rem}
header{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}
h1{font-size:clamp(1.6rem,3vw,2.3rem);margin:.2rem 0}
h2{font-size:1.2rem;margin-top:0}
.muted{color:#a9b5cc}
.panel{background:#151d32;border:1px solid #2b3752;padding:1.5rem;border-radius:18px;margin:1.25rem 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem}
.stat{background:#10172b;border-radius:12px;padding:1rem}
.stat small{display:block;color:#a9b5cc}
.stat strong{font-size:1.15rem;overflow-wrap:anywhere}
.actions{display:flex;flex-wrap:wrap;gap:.7rem}
button{font:inherit;border:0;border-radius:11px;background:#416eec;color:white;padding:.75rem 1rem;font-weight:650;cursor:pointer}
button:hover{filter:brightness(1.15)}
button.warning{background:#af6421}
button.danger{background:#a73548}
button.secondary{background:#34415d}
button:focus-visible,input:focus-visible{outline:3px solid #91baff;outline-offset:2px}
a.bot-link{color:#dbe7ff;text-decoration:none;background:#273a62;border:1px solid #3a4f7c;border-radius:10px;padding:.6rem .9rem}a.bot-link.selected{background:#426ce0;color:#fff}input[type=text],input[type=number]{width:100%;padding:.75rem;border-radius:9px;border:1px solid #687491;background:#111a30;color:#fff;margin:.4rem 0}input[type=password]{width:100%;padding:.85rem;border-radius:9px;border:1px solid #687491;background:#111a30;color:#fff;margin:.5rem 0 1.2rem}
label{display:block}
.notice{padding:.9rem 1rem;border-radius:11px;margin:1rem 0;background:#1b3a37}
/* Acknowledgements vanish after 6 seconds; warnings and errors remain visible. */
.notice.success{overflow:hidden;animation:success-notice-dismiss 6s ease-in forwards}
@keyframes success-notice-dismiss{
  0%,78%{opacity:1;max-height:180px;padding:.9rem 1rem;margin:1rem 0;visibility:visible}
  99%{opacity:0;max-height:0;padding:0 1rem;margin:0;visibility:visible}
  100%{opacity:0;max-height:0;padding:0;border-width:0;margin:0;visibility:hidden}
}
.error{background:#512633}
fieldset{border:1px solid #3c4968;border-radius:12px;margin:1rem 0}
legend{padding:0 .5rem}
form{margin:0}
footer{color:#a9b5cc;margin:2rem 0;font-size:.85rem}

.avatar-heading{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}
.avatar-heading h2,.chosen-bot h2{margin:0}
.avatar-heading p{font-size:.85rem;margin:.2rem 0 0}
.add-link{background:#416eec;border-radius:9px;color:white;text-decoration:none;padding:.5rem .9rem;font-weight:650}
.avatar-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.7rem;margin-top:1rem}
.avatar-item{display:flex;align-items:center;gap:.65rem;min-width:0;background:#10172b;border:1px solid #354462;border-radius:12px;padding:.8rem;color:#e8edf9;text-decoration:none}
.avatar-item:hover{border-color:#85a7f3}
.avatar-item.selected{border-color:#779aff;background:#273f70}
.avatar-dot{color:#83d2a7}
.avatar-text{display:flex;flex-direction:column;min-width:0;flex:1}
.avatar-text strong,.avatar-text small{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.avatar-text small{font-size:.78rem;color:#a9b5cc}
.chosen-bot{display:flex;align-items:center;gap:.85rem;margin:1.3rem 0 .4rem;padding:0 .5rem}
.chosen-bot h2{font-size:1.45rem}
.chosen-bot small{font-size:.8rem}
details.folded{padding:0}
details.folded>summary{display:flex;justify-content:space-between;gap:1rem;align-items:center;cursor:pointer;padding:1.15rem 1.5rem;font-size:1.1rem;font-weight:650;list-style:none}
details.folded>summary::-webkit-details-marker{display:none}
details.folded>summary:after{content:"+";font-size:1.4rem}
details.folded[open]>summary:after{content:"−"}
details.folded>summary small{font-size:.77rem;color:#a9b5cc;font-weight:400;margin-left:auto}
.folded-content{padding:0 1.5rem 1.5rem}
@media(max-width:600px){main{margin:1.4rem auto}.avatar-list{grid-template-columns:1fr}details.folded>summary{padding:1rem}details.folded>summary small{display:none}.folded-content{padding:0 1rem 1rem}}

.admin-menu{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;margin:1rem 0 1.4rem;padding:.45rem;background:#151d32;border:1px solid #2b3752;border-radius:13px}
.admin-menu a{color:#cbd6ec;text-decoration:none;padding:.7rem 1rem;border-radius:10px;font-size:.95rem;font-weight:600}
.admin-menu a:hover{background:#253554}
.admin-menu a[aria-current="page"]{background:#416eec;color:#fff}
.quick-switch{margin-bottom:.5rem}
.module-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.9rem}
.module-grid .stat strong{display:block;font-size:1rem}
.module-grid .stat small{margin-top:.4rem}
@media(max-width:600px){.admin-menu{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.25rem}.admin-menu a{text-align:center;padding:.65rem .3rem;font-size:.8rem}}
.avatar-entry{min-width:0}
.avatar-delete{margin-top:.4rem;border:1px solid #493946;border-radius:9px;padding:.35rem .6rem;font-size:.82rem}
.avatar-delete>summary{cursor:pointer;color:#e4a8af}
.avatar-delete form{padding:.7rem .2rem}
.avatar-delete input[type=text]{font-size:.9rem}
.avatar-delete button{margin-top:.6rem}
.confirm-line{display:flex;gap:.5rem;align-items:center;margin:.75rem 0}
.protected-bot{display:block;padding:.4rem .3rem;font-size:.75rem}

textarea,select{width:100%;padding:.75rem;border-radius:9px;border:1px solid #687491;background:#111a30;color:#fff;margin:.4rem 0 1rem;font:inherit}
textarea{resize:vertical}
</style>
</head>
<body>
<main>
<header>
<div><p class="muted">OPENSIM AI BRIDGE · V0.2 preview</p><h1>Administration BloodMoon AI</h1></div>
<?php if ($authenticated): ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<input type="hidden" name="page" value="<?= esc($page) ?>">
<button class="secondary" name="action" value="logout">Déconnexion</button>
</form>
<?php endif ?>
</header>
<?php if ($authenticated && !empty($fleet['maintenance'])): ?><div class="notice error">Maintenance générale active. <a href="?page=maintenance">Gérer les services</a></div><?php endif ?>
<?php if ($message !== ''): ?><div class="notice success" role="status"><?= esc($message) ?></div><?php endif ?>
<?php if ($error !== ''): ?><div class="notice error" role="alert"><?= esc($error) ?></div><?php endif ?>
<?php if (!$authenticated): ?>
<section class="panel">
<h2>Connexion administrateur</h2>
<p class="muted">Accès réservé au responsable de la grille. Le mot de passe Web est distinct du mot de passe de l'avatar.</p>
<form method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<label for="password">Mot de passe</label>
<input id="password" type="password" name="password" autocomplete="current-password" required>
<button name="action" value="login">Se connecter</button>
</form>
</section>
<?php else: ?>
<nav class="admin-menu" aria-label="Menu principal">
<?php foreach (['dashboard'=>'Tableau de bord','avatars'=>'Mes avatars','settings'=>'Configuration','maintenance'=>'Maintenance générale','modules'=>'Modules IA','knowledge'=>'Base de connaissances'] as $p => $label): ?>
<a href="?page=<?= esc($p) ?>&amp;bot=<?= esc($selectedBot) ?>" <?= $page === $p ? 'aria-current="page"' : '' ?>><?= esc($label) ?></a>
<?php endforeach ?>
</nav>
<?php if ($page === 'avatars'): ?>

<section class="panel">
<div class="avatar-heading"><div><h2>Mes avatars</h2><p class="muted">Choisis un avatar pour gérer son état et ses paramètres.</p></div><a class="add-link" href="#ajouter-avatar">+ Ajouter</a></div>
<?php if ($bots): ?>
<nav class="avatar-list" aria-label="Sélection des avatars">
<?php foreach ($bots as $bot): ?>
<?php $botFullName = trim((string) ($bot['firstName'] ?? '') . ' ' . (string) ($bot['lastName'] ?? '')); ?>
<div class="avatar-entry">
<a class="avatar-item <?= $selectedBot === ($bot['id'] ?? '') ? 'selected' : '' ?>" href="?page=dashboard&amp;bot=<?= urlencode((string) ($bot['id'] ?? 'main')) ?>" <?= $selectedBot === ($bot['id'] ?? '') ? 'aria-current="page"' : '' ?>>
<span class="avatar-dot" aria-hidden="true">●</span><span class="avatar-text"><strong><?= esc($botFullName) ?></strong><small><?= esc((string) ($bot['region'] ?? '')) ?></small></span><span aria-hidden="true">›</span>
</a>
<?php if (($bot['id'] ?? '') !== 'main'): ?>
<details class="avatar-delete">
<summary>Supprimer ce bot</summary>
<form method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="avatars">
<input type="hidden" name="botId" value="<?= esc((string) $bot['id']) ?>">
<p class="muted">Arrête et désactive son service, puis efface sa configuration et son mot de passe privés. Le compte OpenSimulator reste intact.</p>
<label>Pour confirmer, écris exactement <strong><?= esc($botFullName) ?></strong> :</label>
<input type="text" name="confirm_name" autocomplete="off" required placeholder="<?= esc($botFullName) ?>">
<label class="confirm-line"><input type="checkbox" name="delete_confirm" value="yes" required> Je confirme la suppression définitive de ce bot.</label>
<button class="danger" name="action" value="delete_bot">Supprimer <?= esc($botFullName) ?></button>
</form>
</details>
<?php else: ?>
<small class="muted protected-bot">Avatar principal protégé</small>
<?php endif ?>
</div>
<?php endforeach ?>
</nav>
<?php else: ?>
<p class="muted">Liste des avatars indisponible : contrôleur multi-avatars à vérifier.</p>
<?php endif ?>
</section>
<details class="panel folded" id="ajouter-avatar" <?= $error !== '' && ($_POST['action'] ?? '') === 'create_bot' ? 'open' : '' ?>>
<summary>Ajouter et connecter un avatar <small>Prénom, nom, mot de passe, région, position</small></summary>
<div class="folded-content">
<p class="muted">Le compte doit déjà exister sur la grille. Chaque avatar aura ses propres paramètres et son service.</p>
<form method="post" autocomplete="off">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<div class="grid">
<div><label for="new-first">Prénom</label><input type="text" id="new-first" name="firstName" maxlength="32" required></div>
<div><label for="new-last">Nom</label><input type="text" id="new-last" name="lastName" maxlength="32" required></div>
</div>
<label for="new-password">Mot de passe du compte avatar</label>
<input type="password" id="new-password" name="avatarPassword" autocomplete="new-password" required>
<label for="new-region">Région de départ</label>
<input type="text" id="new-region" name="newRegion" maxlength="80" value="BloodMoon_TEST" required>
<div class="grid" style="margin:1rem 0">
<div><label for="new-x">X</label><input type="number" id="new-x" name="x" min="0" max="8192" value="128" required></div>
<div><label for="new-y">Y</label><input type="number" id="new-y" name="y" min="0" max="8192" value="128" required></div>
<div><label for="new-z">Z</label><input type="number" id="new-z" name="z" min="0" max="4096" value="25" required></div>
</div>
<button name="action" value="create_bot" <?= !$bots ? 'disabled' : '' ?>>Ajouter et connecter</button>
</form>
</div>
</details>
<?php endif ?>
<?php if ($page === 'dashboard'): ?>
<section class="panel quick-switch">
<div class="avatar-heading">
<div><h2>Avatar sélectionné : <?= esc($selectedName) ?></h2><p class="muted">Commandes et présence de cet avatar uniquement.</p></div>
<a class="add-link" href="?page=avatars&amp;bot=<?= esc($selectedBot) ?>">Changer d'avatar</a>
</div>
</section>
<div class="chosen-bot"><span class="avatar-dot">●</span><div><small class="muted">Tableau de bord</small><h2><?= esc($selectedName) ?></h2></div></div>
<section class="panel">
<h2>État du service</h2>
<?php if ($state === null): ?>
<div class="notice error">Contrôleur indisponible : aucune commande ne peut être effectuée.</div>
<?php else: ?>
<div class="grid">
<div class="stat"><small>Service</small><strong><?= esc((string) ($state['active'] ?? 'inconnu')) ?></strong></div>
<div class="stat"><small>Sous-état</small><strong><?= esc((string) ($state['substate'] ?? 'inconnu')) ?></strong></div>
<div class="stat"><small>Démarrage au reboot du serveur</small><strong><?= esc((string) ($state['enabled'] ?? 'inconnu')) ?></strong></div>
<div class="stat"><small>Mode Firestorm</small><strong><?= !empty($state['maintenance']) ? 'Activé' : 'Désactivé' ?></strong></div>
<div class="stat"><small>Mémoire RAM</small><strong><?= isset($state['resources']['memoryMb']) ? esc(number_format((float) $state['resources']['memoryMb'], 1, ',', ' ')) . ' Mo' : '—' ?></strong></div>
<div class="stat"><small>CPU du service</small><strong><?= isset($state['resources']['cpuPercent']) ? esc(number_format((float) $state['resources']['cpuPercent'], 1, ',', ' ')) . ' %' : '—' ?></strong></div>
</div>
<p class="muted">« active » indique que le service fonctionne. La RAM représente la mémoire comptabilisée pour ce service, et le CPU sa consommation moyenne entre deux relevés (100 % = un cœur entièrement utilisé ; une valeur supérieure à 100 % est possible). Le CPU affiche « — » au premier relevé ou si les statistiques sont indisponibles. « disabled » concerne le démarrage au reboot.</p>
<?php endif ?>
</section>
<section class="panel">
<h2>Présence et position de l'avatar</h2>
<p class="muted">État réel de la grille · actualisation automatique toutes les 10 secondes.</p>
<?php $avatar = is_array($state['avatar'] ?? null) ? $state['avatar'] : null; ?>
<?php if ($avatar !== null && ($avatar['connected'] ?? false) === true && is_array($avatar['position'] ?? null)): ?>
<div class="grid">
<div class="stat"><small>Connexion grille</small><strong>En ligne</strong></div>
<div class="stat"><small>Région</small><strong><?= esc((string) ($avatar['region'] ?? 'Inconnue')) ?></strong></div>
<div class="stat"><small>Position X / Y / Z</small><strong><?= esc(number_format((float) ($avatar['position']['x'] ?? 0), 2, '.', '')) ?> / <?= esc(number_format((float) ($avatar['position']['y'] ?? 0), 2, '.', '')) ?> / <?= esc(number_format((float) ($avatar['position']['z'] ?? 0), 2, '.', '')) ?></strong></div>
<div class="stat"><small>Dernière mesure</small><strong><?= esc((string) ($avatar['ageSeconds'] ?? '?')) ?> s</strong></div>
</div>
<?php else: ?>
<p class="muted">Position indisponible : le bot est arrêté, hors connexion, ou la version installée ne transmet pas encore les coordonnées. Une mise à jour du bot et du contrôleur est nécessaire pour l'affichage en direct.</p>
<?php endif ?>
</section>
<section class="panel">
<h2>Service de <?= esc($selectedName) ?></h2><p class="muted">Ces commandes agissent uniquement sur cet avatar. <a href="?page=maintenance&amp;bot=<?= esc($selectedBot) ?>">Arrêter tous les services AI</a></p>
<div class="actions">
<?php foreach ([['start','Démarrer',''],['stop','Arrêter','danger'],['restart','Redémarrer','warning'],['firestorm','Mode Firestorm','secondary']] as $btn): ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<button class="<?= esc($btn[2]) ?>" name="action" value="<?= esc($btn[0]) ?>" <?= $state === null ? 'disabled' : '' ?>><?= esc($btn[1]) ?></button>
</form>
<?php endforeach ?>
</div>
</section>
<?php if (!empty($state['maintenance'])): ?>
<section class="panel">
<h2>Reconnecter le bot après Firestorm</h2>
<p class="muted">Ferme complètement Firestorm avec le compte <?= esc($selectedName) ?> avant de relancer le bot.</p>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<fieldset><legend>Confirmation</legend>
<label><input type="checkbox" name="viewer_closed" value="yes" required> Firestorm est déconnecté de ce compte.</label>
</fieldset>
<button name="action" value="resume" <?= $state === null ? 'disabled' : '' ?>>Réactiver <?= esc($selectedName) ?></button>
</form>
</section>
<?php endif ?>
<?php endif ?>
<?php if ($page === 'settings'): ?>
<section class="panel"><h2>Configuration de <?= esc($selectedName) ?></h2><p class="muted">Les modifications sont appliquées au prochain démarrage de cet avatar uniquement. <a href="?page=avatars&amp;bot=<?= esc($selectedBot) ?>">Choisir un autre avatar</a></p></section>
<details class="panel folded" id="configuration" open><summary>Configuration de l'avatar <small>Région, coordonnées et comportement</small></summary><div class="folded-content">
<p class="muted">Choisis une région avec des coordonnées fixes, ou laisse OpenSimulator reconnecter <?= esc($selectedName) ?> à son dernier emplacement enregistré. Un redémarrage du bot applique le choix, sans déplacer immédiatement l'avatar connecté.</p>
<?php if ($botSettings === null): ?>
<p class="muted">Les paramètres ne sont pas encore accessibles. Mets à jour le contrôleur local pour activer leur édition.</p>
<?php else: ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<fieldset><legend>Lieu de connexion</legend>
<label style="margin:.6rem 0"><input type="radio" name="startMode" value="region" <?= ($botSettings['startMode'] ?? 'region') !== 'last' ? 'checked' : '' ?>> Région et coordonnées personnalisées</label>
<label style="margin:.6rem 0"><input type="radio" name="startMode" value="last" <?= ($botSettings['startMode'] ?? 'region') === 'last' ? 'checked' : '' ?>> Dernier emplacement enregistré sur la grille</label>
<p class="muted">En mode « Dernier emplacement », OpenSimulator utilise la dernière position connue de l'avatar. Les coordonnées ci-dessous restent mémorisées pour un éventuel retour au mode personnalisé.</p>
</fieldset>
<div id="manual-start-fields">
<label for="region">Région de démarrage</label>
<input type="text" id="region" name="region" maxlength="80" required value="<?= esc((string) ($botSettings['region'] ?? '')) ?>">
<div class="grid" style="margin:1rem 0">
<?php foreach (['x' => 8192, 'y' => 8192, 'z' => 4096] as $axis => $max): ?>
<div>
<label for="position-<?= esc($axis) ?>">Position <?= strtoupper($axis) ?></label>
<input type="number" id="position-<?= esc($axis) ?>" name="<?= esc($axis) ?>" min="0" max="<?= $max ?>" step="1" required value="<?= esc((string) ($botSettings[$axis] ?? 0)) ?>">
</div>
<?php endforeach ?>
</div>
</div>
<script>
(function () {
    const options = document.querySelectorAll('input[name="startMode"]');
    const fields = document.getElementById('manual-start-fields');
    if (!fields || !options.length) return;
    function refresh() {
        const last = document.querySelector('input[name="startMode"]:checked')?.value === 'last';
        fields.hidden = last;
        fields.querySelectorAll('input').forEach(input => { input.disabled = false; });
    }
    options.forEach(option => option.addEventListener('change', refresh));
    refresh();
})();
</script>
<fieldset><legend>Fonctionnement</legend>
<?php foreach (['enableIM' => 'Répondre aux IM', 'enableLocalChat' => 'Observer le chat local', 'reconnectEnabled' => 'Reconnexion automatique après déconnexion'] as $key => $label): ?>
<label style="margin:.6rem 0"><input type="checkbox" name="<?= esc($key) ?>" value="1" <?= !empty($botSettings[$key]) ? 'checked' : '' ?>> <?= esc($label) ?></label>
<?php endforeach ?>
</fieldset>
<button name="action" value="save_settings">Enregistrer la configuration</button>
</form>
<?php endif ?>
</div></details>
<?php endif ?>
<?php if ($page === 'maintenance'): ?>
<section class="panel">
<h2>Maintenance générale — tous les avatars</h2>
<p class="muted">Arrête ou relance uniquement les services OpenSim AI Bridge : BloodMoon AI, Jolie Candy et les futurs bots. ROBUST, Money et les simulateurs ne sont pas concernés.</p>
<?php if ($fleet === null): ?>
<div class="notice error">État global indisponible. Le contrôleur doit être mis à jour.</div>
<?php else: ?>
<div class="grid">
<div class="stat"><small>Services AI enregistrés</small><strong><?= esc((string) ($fleet['total'] ?? '?')) ?></strong></div>
<div class="stat"><small>Services en cours</small><strong><?= esc((string) ($fleet['running'] ?? '?')) ?></strong></div>
<div class="stat"><small>Verrou global</small><strong><?= !empty($fleet['maintenance']) ? 'Actif' : 'Inactif' ?></strong></div>
</div>
<?php if (empty($fleet['maintenance'])): ?>
<p>Cette opération arrête tous les bots et empêche leur redémarrage, y compris après reboot, pendant le remplacement de DLL communes.</p>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="maintenance">
<fieldset><legend>Confirmation</legend><label><input type="checkbox" name="fleet_confirm" value="yes" required> Confirmer l'arrêt général des avatars AI.</label></fieldset>
<button class="danger" name="action" value="fleet_stop">Arrêter tous les bots et verrouiller</button>
</form>
<?php else: ?>
<p>Maintenance active. Après la mise à jour, seuls les bots actifs avant l'arrêt seront relancés. Les modes Firestorm individuels seront conservés.</p>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="maintenance">
<fieldset><legend>Confirmation</legend><label><input type="checkbox" name="fleet_confirm" value="yes" required> La mise à jour est terminée, autoriser les reconnexions.</label></fieldset>
<button name="action" value="fleet_resume">Terminer la maintenance et relancer</button>
</form>
<?php endif ?>
<?php endif ?>
</section>
<?php endif ?>
<?php if ($page === 'knowledge'): ?>
<section class="panel">
<h2>Base de connaissances BloodMoon</h2>
<p class="muted">Index partagé des pages publiques BloodMoon Grid, Roleplay, Marketplace et OpenSim Handbook. Les PDF du Grimoire liés au guide Roleplay sont inclus. Les discussions IM ne sont pas interrompues pendant l'indexation.</p>
<?php if ($kb === null): ?>
<div class="notice error">État documentaire indisponible : contrôleur à mettre à jour.</div>
<?php else: ?>
<?php
$kbSyncLabel = $kbRunning ? 'Indexation en cours'
    : (($kb['service'] ?? '') === 'failed' || ($kb['result'] ?? '') === 'exit-code'
        ? 'Terminée avec erreurs'
        : (($kb['result'] ?? '') === 'success' && !empty($kb['finishedAt'])
            ? 'Terminée avec succès' : 'Pas de synchronisation récente confirmée'));
?>
<p><strong>Synchronisation :</strong> <?= esc($kbSyncLabel) ?></p>
<?php if (!empty($kb['finishedAt'])): ?><p class="muted"><strong>Dernière fin :</strong> <?= esc($kb['finishedAt']) ?></p><?php endif ?>
<p><strong>Fichier SQLite :</strong> <?= !empty($kb['database']) ? 'Présent' : 'Pas encore créé' ?></p>
<table style="width:100%;text-align:left;border-spacing:0 .6rem">
<thead><tr><th>Source</th><th>Pages / PDF</th><th>Passages</th></tr></thead>
<tbody>
<?php foreach (['grid'=>'BloodMoon Grid','roleplay'=>'Roleplay et PDF','marketplace'=>'Marketplace','handbook'=>'OpenSim Handbook'] as $key => $name):
$found = null;
foreach (($kb['sources'] ?? []) as $entry) { if (($entry['source'] ?? '') === $key) { $found = $entry; break; } } ?>
<tr><td><?= esc($name) ?></td><td><?= (int)($found['pages'] ?? 0) ?></td><td><?= (int)($found['passages'] ?? 0) ?></td></tr>
<?php endforeach ?>
</tbody></table>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="knowledge">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<button name="action" value="knowledge_refresh" <?= $kbRunning ? 'disabled' : '' ?>><?= $kbRunning ? 'Indexation en cours…' : 'Actualiser l\'indexation des quatre sites' ?></button>
</form>
<p class="muted">Ce bouton actualise uniquement les quatre sites et leurs PDF. L'indexation des fiches TXT est distincte.</p>
<hr>
<h3>Fiches locales AI_Knowledge (.txt)</h3>
<p class="muted">Dépose tes documents UTF-8 dans <code><?= esc((string)($kb['localDirectory'] ?? '/var/www/BloodMoon/AI_Knowledge')) ?></code>. Les fichiers sont privés, mais leurs informations alimentent les réponses dans toutes les langues. Ils sont réindexés automatiquement toutes les cinq minutes, indépendamment de l'indexation des sites.</p>
<?php
$localNames = [
    'local_marketplace' => 'marketplace',
    'local_opensim' => 'opensim',
    'local_grid_bloodmoon' => 'grid_bloodmoon',
    'local_roleplay_bloodmoon' => 'roleplay_bloodmoon',
];
?>
<table style="width:100%;text-align:left;border-spacing:0 .6rem">
<thead><tr><th>Dossier</th><th>Fichiers TXT indexés</th><th>Passages</th></tr></thead>
<tbody>
<?php foreach ($localNames as $key => $name):
$found = null;
foreach (($kb['sources'] ?? []) as $entry) { if (($entry['source'] ?? '') === $key) { $found = $entry; break; } } ?>
<tr><td><?= esc($name) ?></td><td><?= (int)($found['pages'] ?? 0) ?></td><td><?= (int)($found['passages'] ?? 0) ?></td></tr>
<?php endforeach ?>
</tbody></table>
<p><strong>Indexation locale :</strong>
<?php
$localState = (string)($kb['localService'] ?? 'unknown');
$localResult = (string)($kb['localResult'] ?? 'unknown');
echo esc(in_array($localState, ['active', 'activating'], true)
    ? 'En cours' : ($localResult === 'success'
        ? 'Dernière exécution réussie' : 'État : ' . $localState . ' / ' . $localResult));
?>
</p>
<?php if (!empty($kb['localFinishedAt'])): ?>
<p class="muted">Dernier passage : <?= esc((string)$kb['localFinishedAt']) ?></p>
<?php endif ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="knowledge">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<button name="action" value="knowledge_local_refresh" <?= in_array($localState, ['active', 'activating'], true) ? 'disabled' : '' ?>><?= in_array($localState, ['active', 'activating'], true) ? 'Indexation des fiches en cours…' : 'Réindexer les fiches TXT maintenant' ?></button>
</form>
<p class="muted">Les compteurs augmentent après indexation des fichiers. Actualise la page pour voir le résultat ; aucune interruption des avatars IA.</p>
<?php endif ?>
</section>
<?php endif ?>
<?php if ($page === 'knowledge'): ?>
<section class="panel">
<h2>Vocabulaire protégé et termes BloodMoon</h2>
<p class="muted">Ajoute les noms qui doivent rester reconnaissables malgré une traduction Azure approximative. Chaque terme peut avoir des variantes (séparées par des virgules), des mots-clés à rechercher dans les documents et une catégorie documentaire. Les changements s'appliquent à tous les avatars, sans redémarrage ni réindexation des TXT.</p>
<?php if ($vocabulary === null): ?>
<div class="notice error">Vocabulaire indisponible : contrôleur local à mettre à jour.</div>
<?php else: ?>
<?php foreach ($vocabulary as $item): ?>
<form method="post" class="panel" style="margin: .8rem 0">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="knowledge">
<input type="hidden" name="previous" value="<?= esc((string)($item['term'] ?? '')) ?>">
<div class="grid">
<div><label>Terme protégé</label><input name="term" maxlength="60" required value="<?= esc((string)($item['term'] ?? '')) ?>"></div>
<div><label>Variantes / synonymes (virgules)</label><input name="aliases" maxlength="900" value="<?= esc((string)($item['aliases'] ?? '')) ?>"></div>
<div><label>Mots-clés documentaires (virgules)</label><input name="keywords" maxlength="900" required value="<?= esc((string)($item['keywords'] ?? '')) ?>"></div>
<div><label>Catégorie documentaire</label>
<select name="domain">
<?php foreach ([''=>'Automatique / toutes','grid'=>'BloodMoon Grid','roleplay'=>'Roleplay','marketplace'=>'Marketplace','handbook'=>'OpenSim Handbook'] as $value => $label): ?>
<option value="<?= esc((string)$value) ?>" <?= ($item['domain'] ?? '') === $value ? 'selected' : '' ?>><?= esc($label) ?></option>
<?php endforeach ?>
</select></div>
</div>
<div class="actions">
<button name="action" value="vocabulary_upsert">Enregistrer les modifications</button>
<button class="danger" name="action" value="vocabulary_delete" formnovalidate>Supprimer ce terme</button>
</div>
</form>
<?php endforeach ?>
<h3>Ajouter un terme protégé</h3>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="page" value="knowledge">
<input type="hidden" name="previous" value="">
<div class="grid">
<div><label>Terme protégé</label><input name="term" maxlength="60" required placeholder="Ex. Soul Reaper"></div>
<div><label>Variantes (séparées par des virgules)</label><input name="aliases" maxlength="900" placeholder="Ex. Reaper"></div>
<div><label>Mots-clés documentaires</label><input name="keywords" maxlength="900" required placeholder="Ex. soul, reaper, âme"></div>
<div><label>Catégorie documentaire</label><select name="domain">
<option value="">Automatique / toutes</option><option value="grid">BloodMoon Grid</option><option value="roleplay">Roleplay</option><option value="marketplace">Marketplace</option><option value="handbook">OpenSim Handbook</option>
</select></div>
</div>
<button name="action" value="vocabulary_upsert">Ajouter ce terme</button>
</form>
<p class="muted">Maximum 100 termes, 12 variantes et 16 mots-clés par entrée. Les données restent dans la configuration privée du serveur, jamais dans le dossier Web.</p>
<?php endif ?>
</section>
<?php endif ?>
<?php if ($page === 'modules'): ?>
<section class="panel">
<h2>IA de <?= esc($selectedName) ?></h2>
<p class="muted">Tous les avatars utilisent exactement les mêmes fournisseurs, modèles, priorités et clés API. Seule l'activation de l'IA est propre à cet avatar.</p>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<input type="hidden" name="page" value="modules">
<label><input type="checkbox" name="avatarAiEnabled" value="1" <?= $avatarAiEnabled ? 'checked' : '' ?>> Activer l'IA pour cet avatar</label>
<button name="action" value="set_avatar_ai_enabled">Enregistrer l'activation de cet avatar</button>
</form>
</section>
<section class="panel">
<h2>Configuration multi-IA globale</h2>
<p class="muted">Une chaîne de moteurs IA distants, ordonnée par priorité. Le premier moteur actif et testé est utilisé ; le mode multi-IA tente le suivant si le précédent est indisponible ou limité. Tous les résidents peuvent dialoguer en IM avec cet avatar lorsqu'au moins un moteur public approuvé est activé.</p>
<?php if ($multiSettings === null): ?>
<div class="notice error">Paramètres multi-IA indisponibles : contrôleur à mettre à jour.</div>
<?php else: ?>
<?php
$profiles = is_array($multiSettings['profiles'] ?? null) ? $multiSettings['profiles'] : [];
$providersAlready = array_column($profiles, 'provider');
foreach (['OpenRouter' => 'openrouter/free', 'Gemini' => 'gemini-3.5-flash-lite'] as $provider => $model) {
    if (!in_array($provider, $providersAlready, true))
        $profiles[] = ['id' => strtolower($provider), 'provider' => $provider, 'model' => $model,
                       'enabled' => false, 'verified' => false, 'hasKey' => false];
}
?>
<form method="post" autocomplete="off" id="multi-ai-form">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<input type="hidden" name="page" value="modules">
<fieldset><legend>Fonctionnement</legend>
<label><input type="checkbox" name="aiEnabled" value="1" <?= !empty($multiSettings['enabled']) ? 'checked' : '' ?>> Autoriser la chaîne de moteurs globale (pour les avatars dont l’IA est activée)</label>
<label for="ai-mode">Mode de fonctionnement</label>
<select id="ai-mode" name="aiMode">
<option value="single" <?= ($multiSettings['mode'] ?? 'auto') === 'single' ? 'selected' : '' ?>>IA unique — uniquement pour tester un moteur</option>
<option value="auto" <?= ($multiSettings['mode'] ?? '') === 'auto' ? 'selected' : '' ?>>Multi-IA (par défaut) — basculement automatique selon la priorité</option>
</select>
</fieldset>
<h3>Priorité et configuration des moteurs</h3>
<p class="muted">Utilise ↑ et ↓ pour changer leur ordre. Les moteurs non testés ne sont jamais utilisés. Enregistre d'abord un nouveau modèle ou une nouvelle clé, puis clique sur « Tester ». Un test réel consomme une requête API et peut être facturé si tu as activé la facturation chez le fournisseur.</p>
<div style="display:flex;justify-content:flex-end;margin:.6rem 0">
<button type="button" class="secondary" id="ai-add-profile">+ Ajouter un moteur</button>
</div>
<div id="ai-profile-list">
<?php foreach ($profiles as $index => $entry): ?>
<div class="panel ai-profile" style="margin:.7rem 0;padding:1rem" data-profile-id="<?= esc((string)($entry['id'] ?? '')) ?>">
<div class="row" style="display:flex;gap:.7rem;align-items:center;justify-content:space-between">
<strong class="ai-rank"><?= $index+1 ?>. <?= esc((string)($entry['provider'] ?? '')) ?></strong>
<div class="actions">
<button type="button" class="secondary ai-up" aria-label="Monter le moteur" title="Monter">↑</button>
<button type="button" class="secondary ai-down" aria-label="Descendre le moteur" title="Descendre">↓</button>
<button type="button" class="secondary ai-remove" aria-label="Retirer ce moteur" title="Retirer">×</button>
</div>
</div>
<input type="hidden" data-field="id" value="<?= esc((string)($entry['id'] ?? '')) ?>">
<div class="grid">
<div><label>Fournisseur</label>
<select data-field="provider" class="ai-provider-select">
<?php foreach (['Groq', 'OpenRouter', 'Gemini', 'OpenAI'] as $provider): ?>
<option value="<?= esc($provider) ?>" <?= ($entry['provider'] ?? '') === $provider ? 'selected' : '' ?>><?= esc($provider) ?></option>
<?php endforeach ?>
</select></div>
<div><label>Modèle</label><input type="text" data-field="model" required maxlength="100"
value="<?= esc((string)($entry['model'] ?? '')) ?>" placeholder="Identifiant du modèle"></div>
</div>
<label><input type="checkbox" data-field="enabled" value="1" <?= !empty($entry['enabled']) ? 'checked' : '' ?>> Activer dans la chaîne</label>
<label>Clé API <?= !empty($entry['hasKey']) ? '(déjà enregistrée)' : '(non enregistrée)' ?></label>
<input type="password" data-field="apiKey" maxlength="256" autocomplete="new-password"
placeholder="<?= !empty($entry['hasKey']) ? 'Laisser vide pour conserver la clé' : 'Saisir une clé pour ce fournisseur' ?>">
<div class="row" style="display:flex;justify-content:space-between;align-items:center;gap:1rem">
<small class="muted"><?= !empty($entry['verified']) ? '✅ Modèle testé et approuvé' : '○ À tester avant activation publique' ?></small>
<button type="submit" class="secondary ai-test-button" name="action" value="test_multi_ai_profile:<?= esc((string)($entry['id'] ?? '')) ?>">Tester le modèle enregistré</button>
</div>
</div>
<?php endforeach ?>
</div>
<div class="grid">
<div><label for="ai-hour">Demandes / heure (par avatar)</label>
<input id="ai-hour" type="number" name="maxRequestsPerHour" min="1" max="120" required value="<?= (int)($multiSettings['maxRequestsPerHour'] ?? 30) ?>"></div>
<div><label for="ai-delay">Délai entre les questions d'un résident (secondes)</label>
<input id="ai-delay" type="number" name="minSecondsBetweenRequests" min="5" max="3600" required value="<?= (int)($multiSettings['minSecondsBetweenRequests'] ?? 15) ?>"></div>
</div>
<label for="multi-prompt">Consignes de l'assistant</label>
<textarea id="multi-prompt" name="systemPrompt" rows="3" maxlength="600" required><?= esc((string)($multiSettings['systemPrompt'] ?? '')) ?></textarea>
<p class="muted">Les modèles OpenAI payants ne peuvent pas être approuvés pour le routage public gratuit. Tu peux ajouter plusieurs modèles par fournisseur, jusqu’à 16 profils au total. Les profils OpenRouter et Gemini doivent utiliser un modèle gratuit et réussir leur test. Ce réglage est commun à tous les avatars. Les anciennes clés et paramètres sont conservés pour un retour arrière.</p>
<button name="action" value="save_multi_ai_settings">Enregistrer la configuration multi-IA</button>
</form>
<?php endif ?>
</section>
<script nonce="<?= esc($scriptNonce) ?>">
(function () {
  'use strict';
  var form = document.getElementById('multi-ai-form');
  var list = document.getElementById('ai-profile-list');
  if (!form || !list) return;
  function renumber() {
    var cards = Array.from(list.querySelectorAll('.ai-profile'));
    cards.forEach(function (card, i) {
      card.querySelector('.ai-rank').textContent = (i + 1) + '. ' + card.querySelector('[data-field="provider"]').value;
      card.querySelectorAll('[data-field]').forEach(function (input) {
        input.name = 'profiles[' + i + '][' + input.dataset.field + ']';
      });
      card.querySelector('.ai-up').disabled = i === 0;
      card.querySelector('.ai-down').disabled = i === cards.length - 1;
    });
  }
  var add = document.getElementById('ai-add-profile');
  if (add) add.addEventListener('click', function () {
    if (list.querySelectorAll('.ai-profile').length >= 16) {
      alert('Maximum huit moteurs par avatar.');
      return;
    }
    var next = document.createElement('div');
    var id = 'profile-' + Math.random().toString(36).slice(2, 10);
    next.className = 'panel ai-profile';
    next.style.cssText = 'margin:.7rem 0;padding:1rem';
    next.dataset.profileId = id;
    next.innerHTML = '<div style="display:flex;gap:.7rem;align-items:center;justify-content:space-between">' +
      '<strong class="ai-rank"></strong><div class="actions">' +
      '<button type="button" class="secondary ai-up" aria-label="Monter">↑</button> ' +
      '<button type="button" class="secondary ai-down" aria-label="Descendre">↓</button> ' +
      '<button type="button" class="secondary ai-remove" aria-label="Retirer">×</button>' +
      '</div></div>' +
      '<input type="hidden" data-field="id" value="' + id + '">' +
      '<div class="grid"><div><label>Fournisseur</label>' +
      '<select data-field="provider" class="ai-provider-select">' +
      '<option value="Groq">Groq</option><option value="OpenRouter">OpenRouter</option>' +
      '<option value="Gemini">Gemini</option><option value="OpenAI">OpenAI</option></select></div>' +
      '<div><label>Modèle</label><input type="text" data-field="model" required maxlength="100" value="openai/gpt-oss-20b"></div></div>' +
      '<label><input type="checkbox" data-field="enabled" value="1"> Activer dans la chaîne</label>' +
      '<label>Clé API (facultative si déjà enregistrée pour le fournisseur)</label>' +
      '<input type="password" data-field="apiKey" maxlength="256" autocomplete="new-password" placeholder="Clé privée">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:1rem">' +
      '<small class="muted">○ À tester avant activation publique</small>' +
      '<button class="secondary ai-test-button" name="action" value="test_multi_ai_profile:' + id + '">Tester le modèle enregistré</button>' +
      '</div>';
    list.appendChild(next);
    renumber();
  });
  list.addEventListener('click', function (event) {
    var btn = event.target.closest('button.ai-up, button.ai-down, button.ai-remove');
    if (!btn) return;
    var card = btn.closest('.ai-profile');
    if (btn.classList.contains('ai-remove')) {
      if (list.children.length <= 1) {
        alert('Il faut conserver au moins un profil.');
        return;
      }
      card.remove();
      renumber();
      return;
    }
    if (btn.classList.contains('ai-up') && card.previousElementSibling)
      list.insertBefore(card, card.previousElementSibling);
    else if (btn.classList.contains('ai-down') && card.nextElementSibling)
      list.insertBefore(card.nextElementSibling, card);
    renumber();
  });
  list.addEventListener('change', function (event) {
    if (event.target.matches('.ai-provider-select')) {
      var card = event.target.closest('.ai-profile');
      card.querySelector('.ai-rank').textContent =
        (Array.from(list.children).indexOf(card) + 1) + '. ' + event.target.value;
    }
  });
  renumber();
}());
</script>
<?php endif ?>
<?php endif ?>
<footer>Aucune clé API ou mot de passe avatar n'est stocké dans ce répertoire Web.</footer>
</main>
</body>
</html>
