# Merged on top of pillar/php/init.sls for apps* hosts only (pillar/top.sls).
php:
  opcache:
    memory_consumption: 256
    interned_strings_buffer: 8
    max_accelerated_files: 20000
    jit_buffer_size: 32M
    validate_timestamps: true
    revalidate_freq: 5
