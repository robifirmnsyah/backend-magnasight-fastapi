#!/bin/bash

# Setup environment variables for production deployment
echo "Setting up environment variables..."

# Read existing .env file
if [ -f ".env" ]; then
    source .env
    echo "Loaded base environment variables from .env"
else
    echo "Warning: .env file not found"
fi

# Create production environment file with Firebase secret
if [ ! -z "$FIREBASE_SA_JSON_SECRET" ]; then
    echo "FIREBASE_SA_JSON='$FIREBASE_SA_JSON_SECRET'" > .env.production
    echo "Firebase secret configured for production"
else
    echo "Warning: FIREBASE_SA_JSON_SECRET not provided"
    # Create empty .env.production to avoid docker-compose errors
    touch .env.production
fi

echo "Environment setup completed"
ls -la .env*