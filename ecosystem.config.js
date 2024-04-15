module.exports = {
  apps : [
      {
            name: 'elastic-api',
            script: 'manage.py',
            args: 'runserver 0.0.0.0:8000',
            instances: 1,
            autorestart: true,
            watch: false,
            max_memory_restart: '1G',
      }
  ]
};