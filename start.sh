#!/bin/bash

# Infinite loop to auto-restart every 4 hours
while true
do
  echo "⚡ Starting your bot..."
  python3 -m Thunder
  echo "♻ Restarting after 4 hours..."
  sleep 14400  # 4 hours in seconds
done
