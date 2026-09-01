# Платформенная упаковка форка olcRTC

<!-- ai-generated: landing document for fork-specific packaging. -->

Форк сохраняет историю и ядро официального проекта `openlibrecommunity/olcrtc`. Дополнения находятся отдельно от core и предназначены для воспроизводимой установки одной версии на обе стороны туннеля.

- [Debian 12 VPS](packaging/debian/README.ru.md)
- [Keenetic Entware ARM64](packaging/keenetic/README.ru.md)
- [Веб-панель Keenetic](web/keenetic/README.ru.md)
- [Синхронизация с официальным upstream и релизы](docs/UPSTREAM.ru.md)
- [Матрица ошибок и план проверки](docs/TESTPLAN.ru.md)

Каждый выпуск собирает `linux/amd64` и `linux/arm64` из одного commit, добавляет два платформенных bundle и строгий `manifest.tsv`. Автоматическая синхронизация upstream создаёт pull request, но не меняет основную ветку и не публикует релиз без ручной проверки.

Первая версия Keenetic-пакета предоставляет только локальный SOCKS5 и не меняет маршруты роутера. Это ограничение сделано намеренно для безопасного внедрения.
