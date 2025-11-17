#!/bin/bash

echo "Stopping MovieBrowser Backend..."

# Check if systemd service exists and is active
if systemctl --user is-active --quiet moviebrowser_backend_v1.service 2>/dev/null; then
    echo "Stopping systemd service..."
    systemctl --user stop moviebrowser_backend_v1.service
    echo "MovieBrowser Backend service stopped"
else
    # Fallback: Find and kill the process using port 8077
    PID=$(lsof -ti:8077)
    
    if [ -n "$PID" ]; then
        kill $PID
        echo "Process $PID killed successfully"
        
        # Wait a moment and check if it's still running
        sleep 2
        if lsof -i:8077 > /dev/null 2>&1; then
            echo "Process still running, force killing..."
            kill -9 $PID
        fi
        
        echo "MovieBrowser Backend stopped"
    else
        echo "No process found running on port 8077"
    fi
fi