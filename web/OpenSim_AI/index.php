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
function request_control(string $action, bool $confirm = false): array {
    $errno = 0;
    $errstr = '';
    $fp = @stream_socket_client('unix://' . CONTROL_SOCKET, $errno, $errstr, 2.0);
    if ($fp === false) {
        return ['ok' => false, 'error' => 'Contrôleur local indisponible'];
    }
    stream_set_timeout($fp, 35);
    $sent = fwrite($fp, json_encode(['action' => $action, 'confirm' => $confirm], JSON_THROW_ON_ERROR) . "\n");
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

$now = time();
if (isset($_SESSION['last_activity']) && $now - (int) $_SESSION['last_activity'] > IDLE_SECONDS) {
    $_SESSION = [];
    session_regenerate_id(true);
}
$authenticated = ($_SESSION['admin'] ?? false) === true;
$message = '';
$error = '';

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
        if (in_array($action, $allowed, true)) {
            if ($action === 'resume' && ($_POST['viewer_closed'] ?? '') !== 'yes') {
                $error = 'Confirme d’abord la fermeture de Firestorm.';
            } else {
                $response = request_control($action, $action === 'resume');
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
if ($authenticated) {
    $_SESSION['last_activity'] = $now;
}
$status = $authenticated ? request_control('status') : null;
$state = is_array($status['result'] ?? null) ? $status['result'] : null;
?>
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>BloodMoon AI — Administration</title>
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
input[type=password]{width:100%;padding:.85rem;border-radius:9px;border:1px solid #687491;background:#111a30;color:#fff;margin:.5rem 0 1.2rem}
label{display:block}
.notice{padding:.9rem 1rem;border-radius:11px;margin:1rem 0;background:#1b3a37}
.error{background:#512633}
fieldset{border:1px solid #3c4968;border-radius:12px;margin:1rem 0}
legend{padding:0 .5rem}
form{margin:0}
footer{color:#a9b5cc;margin:2rem 0;font-size:.85rem}
</style>
</head>
<body>
<main>
<header>
<div><p class="muted">OPENSIM AI BRIDGE · V0.2 preview</p><h1>Administration BloodMoon AI</h1></div>
<?php if ($authenticated): ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<button class="secondary" name="action" value="logout">Déconnexion</button>
</form>
<?php endif ?>
</header>
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
<section class="panel">
<h2>État du service</h2>
<?php if ($state === null): ?>
<div class="notice error">Contrôleur indisponible : aucune commande ne peut être effectuée.</div>
<?php else: ?>
<div class="grid">
<div class="stat"><small>Service</small><strong><?= esc((string) ($state['active'] ?? 'inconnu')) ?></strong></div>
<div class="stat"><small>Sous-état</small><strong><?= esc((string) ($state['substate'] ?? 'inconnu')) ?></strong></div>
<div class="stat"><small>Démarrage automatique</small><strong><?= esc((string) ($state['enabled'] ?? 'inconnu')) ?></strong></div>
<div class="stat"><small>Mode Firestorm</small><strong><?= !empty($state['maintenance']) ? 'Activé' : 'Désactivé' ?></strong></div>
</div>
<p class="muted">L'état « active » signifie que le processus tourne. Cela ne garantit pas encore la connexion de l'avatar à la grille.</p>
<?php endif ?>
</section>
<section class="panel">
<h2>Contrôle de l'avatar</h2>
<div class="actions">
<?php foreach ([['start','Démarrer',''],['stop','Arrêter','danger'],['restart','Redémarrer','warning'],['firestorm','Mode Firestorm','secondary']] as $btn): ?>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<button class="<?= esc($btn[2]) ?>" name="action" value="<?= esc($btn[0]) ?>" <?= $state === null ? 'disabled' : '' ?>><?= esc($btn[1]) ?></button>
</form>
<?php endforeach ?>
</div>
</section>
<section class="panel">
<h2>Reprendre après Firestorm</h2>
<p class="muted">Ferme complètement Firestorm avec le compte BloodMoon AI avant de relancer le bot.</p>
<form method="post">
<input type="hidden" name="csrf" value="<?= esc(csrf_token()) ?>">
<fieldset><legend>Confirmation</legend>
<label><input type="checkbox" name="viewer_closed" value="yes" required> Firestorm est déconnecté de ce compte.</label>
</fieldset>
<button name="action" value="resume" <?= $state === null ? 'disabled' : '' ?>>Désactiver le verrou et reprendre</button>
</form>
</section>
<section class="panel">
<h2>Prochaines fonctionnalités</h2>
<p class="muted">FAQ multilingue · Traduction BloodMoon · Autorisations UUID · Fournisseurs IA distants. Ces modules ne sont pas encore actifs.</p>
</section>
<?php endif ?>
<footer>Aucune clé API ou mot de passe avatar n'est stocké dans ce répertoire Web.</footer>
</main>
</body>
</html>
