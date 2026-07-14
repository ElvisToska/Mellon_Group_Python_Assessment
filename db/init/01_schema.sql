-- Βασικό schema του TMS (Terminal Management System) — MySQL.
-- Τρέχει αυτόματα από το MySQL container την ΠΡΩΤΗ φορά που ξεκινάει
-- (docker-entrypoint-initdb.d): https://hub.docker.com/_/mysql
-- Αν θέλετε να ξαναγίνει seed από την αρχή: docker compose down -v && docker compose up -d

CREATE TABLE merchants (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    mid  VARCHAR(20)  NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE templates (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    template_name    VARCHAR(255) NOT NULL,
    hardware_model   VARCHAR(50),
    hardware_family  VARCHAR(50)
);

CREATE TABLE terminals (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    tid               VARCHAR(20)  NOT NULL UNIQUE,
    merchant_id       INT          NOT NULL,
    template_id       INT          NULL,
    serial_number     VARCHAR(50),
    software_version  VARCHAR(20),
    sdk_version       VARCHAR(20),
    scenario_number   VARCHAR(10),
    hardware_model    VARCHAR(50),
    hardware_family   VARCHAR(50),
    enabled           TINYINT(1)   NOT NULL DEFAULT 1,
    created_on        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_call_stamp   DATETIME     NULL,
    FOREIGN KEY (merchant_id) REFERENCES merchants(id),
    FOREIGN KEY (template_id) REFERENCES templates(id)
);
