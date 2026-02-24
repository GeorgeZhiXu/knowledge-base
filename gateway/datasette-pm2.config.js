module.exports = {
  apps: [
    {
      name: 'knowledge-datasette',
      cwd: '/Users/xuzhi/prod/knowledge-base',
      script: '.venv/bin/datasette',
      args: 'serve data/knowledge.db --host 127.0.0.1 --port 8021 --setting base_url /datasette/',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '200M',
      error_file: '/Users/xuzhi/prod/gateway/logs/knowledge-datasette-error.log',
      out_file: '/Users/xuzhi/prod/gateway/logs/knowledge-datasette-out.log',
      time: true,
    }
  ]
};
