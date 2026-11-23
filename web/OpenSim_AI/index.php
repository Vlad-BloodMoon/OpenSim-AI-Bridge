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
header("Content-Security-Policy: default-src 'none'; style-src 'self' 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");

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
$page = is_string($pageRaw) && in_array($pageRaw, ['dashboard', 'avatars', 'settings', 'maintenance', 'modules'], true) ? $pageRaw : 'dashboard';
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
        if ($action === 'fleet_stop' || $action === 'fleet_resume') {
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
            foreach (['x' => 256, 'y' => 256, 'z' => 4096] as $axis => $limit) {
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
        } elseif ($action === 'save_settings') {
            $page = 'settings';
            $region = is_string($_POST['region'] ?? null) ? trim($_POST['region']) : '';
            $coords = [];
            foreach (['x' => 256, 'y' => 256, 'z' => 4096] as $axis => $limit) {
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
<?php if ($message !== ''): ?><div class="notice" role="status"><?= esc($message) ?></div><?php endif ?>
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
<?php foreach (['dashboard'=>'Tableau de bord','avatars'=>'Mes avatars','settings'=>'Configuration','maintenance'=>'Maintenance générale','modules'=>'Modules IA'] as $p => $label): ?>
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
<div><label for="new-x">X</label><input type="number" id="new-x" name="x" min="0" max="256" value="128" required></div>
<div><label for="new-y">Y</label><input type="number" id="new-y" name="y" min="0" max="256" value="128" required></div>
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
<p class="muted">Choisis la région et les coordonnées où <?= esc($selectedName) ?> apparaîtra à sa prochaine connexion. La sauvegarde ne déplace pas immédiatement l'avatar connecté : un redémarrage du bot applique ces paramètres.</p>
<?php if ($botSettings === null): ?>
<p class="muted">Les paramètres ne sont pas encore accessibles. Mets à jour le contrôleur local pour activer leur édition.</p>
<?php else: ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<input type="hidden" name="botId" value="<?= esc($selectedBot) ?>">
<label for="region">Région de démarrage</label>
<input type="text" id="region" name="region" maxlength="80" required value="<?= esc((string) ($botSettings['region'] ?? '')) ?>">
<div class="grid" style="margin:1rem 0">
<?php foreach (['x' => 256, 'y' => 256, 'z' => 4096] as $axis => $max): ?>
<div>
<label for="position-<?= esc($axis) ?>">Position <?= strtoupper($axis) ?></label>
<input type="number" id="position-<?= esc($axis) ?>" name="<?= esc($axis) ?>" min="0" max="<?= $max ?>" step="1" required value="<?= esc((string) ($botSettings[$axis] ?? 0)) ?>">
</div>
<?php endforeach ?>
</div>
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
<?php if ($page === 'modules'): ?>
<section class="panel"><h2>Modules et fonctionnalités</h2>
<p class="muted">Cette rubrique accueillera les réglages individuels ou partagés de chaque assistant. Les fonctionnalités ci-dessous sont prévues, mais pas encore activées.</p>
<div class="module-grid">
<div class="stat"><strong>FAQ et base de connaissances</strong><small>Réponses éditables, documents, comportement par bot</small></div>
<div class="stat"><strong>Traduction</strong><small>Intégration de l'API de traduction BloodMoon</small></div>
<div class="stat"><strong>IA distante</strong><small>Fournisseurs et quotas propres à chaque avatar</small></div>
<div class="stat"><strong>Autorisations et journaux</strong><small>UUID autorisés, historique et diagnostic</small></div>
</div></section>
<?php endif ?>
<?php endif ?>
<footer>Aucune clé API ou mot de passe avatar n'est stocké dans ce répertoire Web.</footer>
</main>
</body>
</html>
