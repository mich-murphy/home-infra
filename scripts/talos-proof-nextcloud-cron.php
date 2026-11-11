<?php
/** Offline-prepared payload. There is deliberately NO admitted mutation path yet.
 * Native methods below are version-bound to the reviewed Nextcloud 35.0.2 core.
 * Do not remove the gate until the guarded supervisor and restoration window exist.
 */
declare(strict_types=1);
umask(0077);
const CLEANUP_CLASS = 'OC\\Authentication\\Token\\TokenCleanupJob';
const MUTATION_INTEGRATION_READY = false;

function need(bool $condition, string $gate): void {
    if (!$condition) { throw new RuntimeException($gate); }
}
function exclusive(string $path, array $value): void {
    $stream = fopen($path, 'x');
    need($stream !== false, 'exclusive private journal creation failed');
    try {
        need(chmod($path, 0600), 'journal permissions failed');
        $data = json_encode($value, JSON_THROW_ON_ERROR);
        need(fwrite($stream, $data) === strlen($data) && fflush($stream), 'journal write failed');
        need(function_exists('fsync') && fsync($stream), 'durable journal fsync unavailable');
    } finally { fclose($stream); }
}
function cgroups(): array {
    $result = [];
    foreach (['memory.current', 'memory.peak', 'memory.events', 'memory.stat'] as $file) {
        $value = @file_get_contents('/sys/fs/cgroup/' . $file);
        $result[$file] = $value === false ? ['gap' => 'unavailable'] : trim($value);
    }
    return $result;
}
function parity(string $root): void {
    $hashes = json_decode(file_get_contents('/proof/core-hashes.json'), true, 512, JSON_THROW_ON_ERROR);
    need(count($hashes) >= 20, 'incomplete reviewed core source index');
    foreach ($hashes as $relative => $hash) {
        need(!str_contains($relative, '..') && $relative[0] !== '/', 'invalid source index');
        $path = $root . '/' . $relative;
        for ($part = $path; $part !== $root; $part = dirname($part)) {
            need(!is_link($part), 'symlink in reviewed source path');
        }
        need(is_file($path) && hash_equals($hash, hash_file('sha256', $path)), 'actual core source parity mismatch');
    }
}
function rows(string $table, array $columns): array {
    $db = \OCP\Server::get(\OCP\IDBConnection::class);
    $qb = $db->getQueryBuilder();
    return $qb->select(...$columns)->from($table)->executeQuery()->fetchAllAssociative();
}
function tokenRows(): array {
    // Physical DB reads only: no cached token getter used as deletion evidence.
    return rows('authtoken', ['id', 'uid', 'name', 'type', 'remember', 'last_activity']);
}
function cleanupRow(): array {
    $found = array_values(array_filter(rows('jobs', ['id','class','last_run','last_checked','reserved_at']),
        fn($r) => $r['class'] === CLEANUP_CLASS));
    need(count($found) === 1, 'cleanup job missing or ambiguous');
    return $found[0];
}
function due(array $job): void {
    need((int)$job['last_run'] >= 0 && time() - (int)$job['last_run'] > 86400
        && (int)$job['reserved_at'] === 0 && (int)$job['last_checked'] <= time(),
        'native daily cleanup not due/unreserved; class filter does not bypass interval');
}
function snapshot($config): array {
    return ['session_lifetime' => [
        'present' => in_array('session_lifetime', $config->getSystemKeys(), true),
        'value' => $config->getSystemValue('session_lifetime')],
        'backgroundjobs_mode' => [
        'present' => in_array('backgroundjobs_mode', $config->getAppKeys('core'), true),
        'value' => $config->getAppValue('core', 'backgroundjobs_mode')]];
}
function nativeContext(): array {
    parity('/usr/src/nextcloud');
    parity('/var/www/html');
    need(is_file('/var/www/html/config/config.php') && !is_link('/var/www/html/config/config.php')
        && fileowner('/var/www/html/config/config.php') === 33, 'retained config ownership invalid');
    require_once '/var/www/html/lib/base.php';
    $config = \OCP\Server::get(\OCP\IConfig::class);
    need($config->getSystemValue('installed') === true && $config->getSystemValue('maintenance', false) === false
        && $config->getSystemValue('version') === '35.0.2.2'
        && $config->getSystemValue('dbtype') === 'pgsql'
        && $config->getSystemValue('dbhost') === 'postgres'
        && $config->getSystemValue('dbname') === 'nextcloud'
        && $config->getSystemValue('dbuser') === 'nextcloud'
        && $config->getSystemValue('datadirectory') === '/var/www/html/data', 'retained native configuration mismatch');
    need(!\OC::checkUpgrade(), 'pending native upgrade blocks');
    need(\OCP\Server::get(\OCP\IUserManager::class)->get('proof') !== null, 'original proof user absent; never recreate/reset');
    $redis = $config->getSystemValue('redis');
    need(is_array($redis) && ($redis['host'] ?? null) === 'redis'
        && ($redis['password'] ?? null) === getenv('REDIS_HOST_PASSWORD')
        && is_string($redis['password']) && $redis['password'] !== '', 'authenticated Redis configuration unverified');
    need($config->getSystemValue('memcache.locking') === '\\OC\\Memcache\\Redis', 'native Redis locking not configured');
    // Read-only connection assertion; never FLUSH/SET/CONFIG.
    $client = new Redis();
    need($client->connect('redis', (int)($redis['port'] ?? 6379), 3.0)
        && $client->auth($redis['password']) && $client->ping() !== false, 'native Redis authentication failed');
    $client->close();
    return [$config, \OCP\Server::get(\OC\Authentication\Token\IProvider::class)];
}
function fixture(string $journal): array {
    [$config, $provider] = nativeContext();
    need(tokenRows() === [], 'retained token state blocks global TTL change');
    $beforeJob = cleanupRow();
    due($beforeJob); // BEFORE any setting/token mutation
    need($config->getSystemValueInt('remember_login_cookie_lifetime', 1296000) > 3600,
        'remembered control retention too short');
    $state = ['settings' => snapshot($config), 'job' => $beforeJob, 'created_at' => time(), 'tokens' => []];
    // Names + raw fixtures are journaled BEFORE the first mutation. Recovery uses
    // unique names, even if the process dies after native insert and before IDs save.
    foreach (['candidate', 'control'] as $kind) {
        $state['tokens'][$kind] = ['name' => 'proof-cron-' . basename($journal) . '-' . $kind,
            'raw' => bin2hex(random_bytes(32)), 'remember' => $kind === 'control'
                ? \OCP\Authentication\Token\IToken::REMEMBER : \OCP\Authentication\Token\IToken::DO_NOT_REMEMBER];
    }
    exclusive($journal . '/before.json', $state);
    $config->setSystemValue('session_lifetime', 5);
    foreach ($state['tokens'] as $token) {
        // NULL password is mandatory: do not call updatePasswords on retained tokens.
        $provider->generateToken($token['raw'], 'proof', 'proof', null, $token['name'],
            \OCP\Authentication\Token\IToken::TEMPORARY_TOKEN, $token['remember']);
    }
    $deadline = hrtime(true) + 10000000000;
    do {
        $physical = tokenRows();
        need(count($physical) === 2, 'native fixture rows missing/unexpected');
        $expired = array_values(array_filter($physical, fn($r) => $r['name'] === $state['tokens']['candidate']['name']));
        need(count($expired) === 1, 'candidate row ambiguous');
        if ((int)$expired[0]['last_activity'] < time() - 5) { break; }
        usleep(100000);
    } while (hrtime(true) < $deadline);
    need((int)$expired[0]['last_activity'] < time() - 5, 'genuine native session age timeout');
    due(cleanupRow());
    exclusive($journal . '/fixture.json', ['rows' => $physical, 'observed_at' => time()]);
    return ['candidate_aged' => true, 'rows' => 2, 'due' => true];
}
function restore(string $journal): void {
    [$config, $provider] = nativeContext();
    $state = json_decode(file_get_contents($journal . '/before.json'), true, 512, JSON_THROW_ON_ERROR);
    // Failure cleanup is distinct from acceptance. Only exact new fixture names
    // with expected user/type/remember are eligible for native invalidation.
    foreach (tokenRows() as $row) {
        foreach ($state['tokens'] as $token) {
            if ($row['name'] !== $token['name']) { continue; }
            need($row['uid'] === 'proof' && (int)$row['type'] === \OCP\Authentication\Token\IToken::TEMPORARY_TOKEN
                && (int)$row['remember'] === $token['remember'], 'synthetic token ownership mismatch');
            $provider->invalidateTokenById('proof', (int)$row['id']);
        }
    }
    $old = $state['settings'];
    if ($old['session_lifetime']['present']) { $config->setSystemValue('session_lifetime', $old['session_lifetime']['value']); }
    else { $config->deleteSystemValue('session_lifetime'); }
    if ($old['backgroundjobs_mode']['present']) { $config->setAppValue('core', 'backgroundjobs_mode', $old['backgroundjobs_mode']['value']); }
    else { $config->deleteAppValue('core', 'backgroundjobs_mode'); }
    need(snapshot($config) === $old, 'exact typed setting restoration failed');
    exclusive($journal . '/restored.json', ['restored_at' => time()]);
}
function assertion(string $journal): array {
    [, $provider] = nativeContext();
    $before = json_decode(file_get_contents($journal . '/fixture.json'), true, 512, JSON_THROW_ON_ERROR);
    $state = json_decode(file_get_contents($journal . '/before.json'), true, 512, JSON_THROW_ON_ERROR);
    $physical = tokenRows();
    $candidate = array_values(array_filter($before['rows'], fn($r) => $r['name'] === $state['tokens']['candidate']['name']));
    $control = array_values(array_filter($before['rows'], fn($r) => $r['name'] === $state['tokens']['control']['name']));
    need(count($candidate) === 1 && count($control) === 1, 'before-state invalid');
    need(count(array_filter($physical, fn($r) => (int)$r['id'] === (int)$candidate[0]['id'])) === 0, 'expired candidate physically survives');
    need(count(array_filter($physical, fn($r) => $r === $control[0])) === 1, 'live control does not survive unchanged');
    $job = cleanupRow();
    need((int)$job['id'] === (int)$state['job']['id'] && (int)$job['last_run'] > (int)$state['job']['last_run']
        && (int)$job['last_run'] >= $before['observed_at'] && (int)$job['last_run'] <= time()
        && (int)$job['reserved_at'] === 0, 'native scheduling metadata did not advance');
    $lastcron = \OCP\Server::get(\OCP\IConfig::class)->getAppValue('core', 'lastcron');
    need(ctype_digit($lastcron) && (int)$lastcron >= $before['observed_at'] && (int)$lastcron <= time(), 'lastcron corroboration missing');
    exclusive($journal . '/acceptance.json', ['candidate_physically_absent' => true,
        'control_physically_survives' => true, 'observed_at' => time()]);
    restore($journal); // native harness cleanup is AFTER acceptance observation
    return ['native_side_effect' => true, 'restored' => true];
}
try {
    $phase = $argv[1] ?? '';
    $run = $argv[2] ?? '';
    need((bool)preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D', $run), 'UUID required');
    if ($phase === 'preflight') {
        parity('/usr/src/nextcloud');
        // No retained PHP config/bootstrap execution in read-only phase. Config
        // evaluation, DB emptiness, Docker fragments and Redis are STILL GATES.
        $root = '/var/www/html';
        need(is_dir($root) && !is_link($root), 'PVC root absent/symlink');
        $entries = array_values(array_diff(scandir($root), ['.', '..']));
        foreach ($entries as $entry) { need(!is_link($root . '/' . $entry), 'retained root contains symlink'); }
        $result = ['core_public_source_parity' => true, 'pvc_root_empty' => $entries === [],
            'retained_state_redis_install_authorized' => false,
            'gate' => 'PVC/DB/Secret identity, full retained inventory, Docker/config parity and read-only Redis preflight unresolved'];
    } else {
        need(MUTATION_INTEGRATION_READY, 'BLOCKED: serial guarded supervisor, retained-state/Redis preflight and durable off-pod recovery journal not implemented');
        // Intentionally unreachable until reviewed integration exists. A setting,
        // receipt field or caller-provided passing value cannot waive this gate.
        $journal = '/var/www/html/.proof-cron-' . $run;
        switch ($phase) {
            case 'fixture': $result = fixture($journal); break;
            case 'assert-restore': $result = assertion($journal); break;
            default: throw new RuntimeException('install-or-verify/cron require reviewed supervisor; never invoke image entrypoint');
        }
    }
    echo json_encode(['phase' => $phase, 'result' => $result, 'cgroups' => cgroups()], JSON_THROW_ON_ERROR) . PHP_EOL;
} catch (Throwable $e) {
    // Never print exception messages: native errors can contain passwords/tokens.
    echo json_encode(['status' => 'BLOCKED_OR_FAILED', 'error_type' => get_class($e), 'cgroups' => cgroups()]) . PHP_EOL;
    exit(1);
}
