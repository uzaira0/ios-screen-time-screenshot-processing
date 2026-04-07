#!/bin/bash
# Create both development and test databases for iOS Screen Time Screenshot Processing

set -e

# Create test database (dev database is created by POSTGRES_DB env var)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE ios_screen_time_screenshot_processing_test;
    GRANT ALL PRIVILEGES ON DATABASE ios_screen_time_screenshot_processing_test TO $POSTGRES_USER;
EOSQL

echo "Test database 'ios_screen_time_screenshot_processing_test' created successfully"
