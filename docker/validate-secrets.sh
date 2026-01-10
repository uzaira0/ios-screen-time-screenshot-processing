#!/bin/bash
# validate-secrets.sh - Validate production secrets before deployment
#
# This script checks that all required secrets are set with sufficient entropy.
# Run this before `docker-compose up` in production.
#
# Usage:
#   ./docker/validate-secrets.sh
#   # Or from docker/ directory:
#   ./validate-secrets.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

log_error() {
    echo -e "${RED}ERROR:${NC} $1"
    ((ERRORS++))
}

log_warning() {
    echo -e "${YELLOW}WARNING:${NC} $1"
    ((WARNINGS++))
}

log_success() {
    echo -e "${GREEN}OK:${NC} $1"
}

check_secret_entropy() {
    local name=$1
    local value=$2
    local min_length=${3:-32}
    local min_unique=${4:-10}

    if [ -z "$value" ]; then
        log_error "$name is not set"
        return 1
    fi

    local length=${#value}
    if [ $length -lt $min_length ]; then
        log_error "$name is too short ($length chars, minimum $min_length)"
        return 1
    fi

    # Count unique characters
    local unique=$(echo "$value" | grep -o . | sort -u | wc -l)
    if [ $unique -lt $min_unique ]; then
        log_error "$name has low entropy ($unique unique chars, minimum $min_unique)"
        return 1
    fi

    # Check for common weak patterns
    if [[ "$value" =~ ^(.)\1+$ ]]; then
        log_error "$name appears to be a repeated character"
        return 1
    fi

    if [[ "$value" == "changeme" || "$value" == "password" || "$value" == "secret" ]]; then
        log_error "$name is a well-known weak secret"
        return 1
    fi

    log_success "$name is properly configured ($length chars, $unique unique)"
    return 0
}

check_postgres_password() {
    if [ -z "$POSTGRES_PASSWORD" ]; then
        log_error "POSTGRES_PASSWORD is not set"
        return 1
    fi
    check_secret_entropy "POSTGRES_PASSWORD" "$POSTGRES_PASSWORD" 16 8
}

check_secret_key() {
    if [ -z "$SECRET_KEY" ]; then
        log_error "SECRET_KEY is not set"
        return 1
    fi
    check_secret_entropy "SECRET_KEY" "$SECRET_KEY" 32 16
}

check_upload_api_key() {
    if [ -z "$UPLOAD_API_KEY" ]; then
        log_error "UPLOAD_API_KEY is not set"
        return 1
    fi
    check_secret_entropy "UPLOAD_API_KEY" "$UPLOAD_API_KEY" 32 12
}

check_debug_mode() {
    if [ "$DEBUG" = "true" ] || [ "$DEBUG" = "True" ] || [ "$DEBUG" = "1" ]; then
        log_warning "DEBUG mode is enabled - disable for production"
    else
        log_success "DEBUG mode is disabled"
    fi
}

check_cors_origins() {
    if [ -z "$CORS_ORIGINS" ]; then
        log_warning "CORS_ORIGINS not set - will use default (localhost only)"
    elif [[ "$CORS_ORIGINS" == *"*"* ]]; then
        log_warning "CORS_ORIGINS contains wildcard (*) - consider restricting"
    else
        log_success "CORS_ORIGINS is configured"
    fi
}

# Main
echo "=========================================="
echo "Screenshot Annotator - Secret Validation"
echo "=========================================="
echo ""

# Load .env file if it exists
if [ -f ".env" ]; then
    echo "Loading .env file..."
    set -a
    source .env
    set +a
elif [ -f "../.env" ]; then
    echo "Loading ../.env file..."
    set -a
    source ../.env
    set +a
else
    log_warning "No .env file found - using environment variables only"
fi

echo ""
echo "Checking required secrets..."
echo ""

check_postgres_password
check_secret_key
check_upload_api_key

echo ""
echo "Checking configuration..."
echo ""

check_debug_mode
check_cors_origins

echo ""
echo "=========================================="

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}FAILED:${NC} $ERRORS error(s), $WARNINGS warning(s)"
    echo ""
    echo "Fix the errors above before deploying to production."
    echo ""
    echo "Generate secure secrets with:"
    echo "  python -c \"import secrets; print(secrets.token_hex(32))\""
    exit 1
else
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}PASSED WITH WARNINGS:${NC} $WARNINGS warning(s)"
    else
        echo -e "${GREEN}PASSED:${NC} All secrets validated"
    fi
    echo ""
    echo "You can now run: docker-compose up -d"
    exit 0
fi
