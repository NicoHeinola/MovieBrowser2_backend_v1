#!/bin/bash

# Auto-start MovieBrowser Backend
echo "Starting MovieBrowser Backend..."

# Check if systemd service exists
if systemctl --user list-unit-files moviebrowser_backend_v1.service &>/dev/null; then
    # Use systemd service
    if systemctl --user is-active --quiet moviebrowser_backend_v1.service; then
        echo "MovieBrowser Backend service is already running"
        systemctl --user status moviebrowser_backend_v1.service --no-pager
    else
        echo "Starting systemd service..."
        systemctl --user start moviebrowser_backend_v1.service
        sleep 2
        if systemctl --user is-active --quiet moviebrowser_backend_v1.service; then
            echo "MovieBrowser Backend service started successfully"
            systemctl --user status moviebrowser_backend_v1.service --no-pager
        else
            echo "Failed to start service. Check logs with: journalctl --user -u moviebrowser_backend_v1 -n 50"
        fi
    fi
else
    echo "Systemd service not found. Run ./scripts/setup_service.sh first."
fi