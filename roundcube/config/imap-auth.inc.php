<?php

$config['imap_auth_type'] = 'PLAIN';
$config['default_user'] = getenv('ARCHIVE_USER') ?: 'archive';
$config['default_pass'] = getenv('ARCHIVE_PASSWORD') ?: 'password';
$config['imap_conn_options'] = [
    'ssl' => [
        'verify_peer' => false,
        'verify_peer_name' => false,
        'allow_self_signed' => true,
    ],
];
