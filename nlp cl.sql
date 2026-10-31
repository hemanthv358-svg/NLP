CREATE USER IF NOT EXISTS 'jssstu_app'@'localhost'
    IDENTIFIED BY 'YOUR_APP_PASSWORD';

ALTER USER 'jssstu_app'@'localhost'
    IDENTIFIED BY 'YOUR_APP_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
    ON jssstu_ai.* TO 'jssstu_app'@'localhost';

SHOW GRANTS FOR 'jssstu_app'@'localhost';
