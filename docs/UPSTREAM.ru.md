# Обновление форка и выпуск бинарников

Этот документ описывает сопровождение форка `qqweqwe287-art/olcrtc`. Форк сохраняет историю официального проекта `openlibrecommunity/olcrtc` и держит платформенную упаковку отдельно от ядра.

## Основные правила

- Официальный репозиторий остается источником ядра и протокола.
- Изменения для Debian и Keenetic находятся в `packaging/`, отдельных workflow и документации форка.
- `master` не обновляется напрямую автоматизацией.
- Синхронизация с upstream создает отдельную ветку и pull request.
- Слияние upstream никогда не создает релиз.
- Релиз запускается только вручную после проверки pull request.
- Сервер и клиент обновляются на бинарники из одного релиза и одного `source_commit`.

Последний включенный commit официального проекта хранится в `packaging/release/UPSTREAM_COMMIT`. Workflow синхронизации обновляет этот файл вместе с кодом.

## Git remotes для локальной работы

После клонирования форка настройте официальный репозиторий как `upstream`:

```sh
git remote add upstream https://github.com/openlibrecommunity/olcrtc.git
git fetch --prune upstream master
git remote -v
```

`origin` должен указывать на форк, а `upstream` на официальный проект. Не меняйте `origin` на официальный репозиторий.

## Безопасная синхронизация через GitHub Actions

Workflow `Propose upstream sync` запускается вручную на вкладке Actions. Он выполняет следующие действия:

1. Получает `openlibrecommunity/olcrtc:master`.
2. Проверяет, включен ли последний upstream commit в форк.
3. Создает ветку `automation/upstream-<sha>`.
4. Делает merge без изменения основной ветки.
5. Записывает upstream SHA в `packaging/release/UPSTREAM_COMMIT`.
6. Запускает короткие тесты с race detector и тест release manifest.
7. Публикует ветку и открывает pull request.

Если merge содержит конфликт или тест не проходит, workflow завершается до публикации ветки. Конфликт нужно разобрать вручную. Не следует автоматически выбирать только сторону форка или только сторону upstream.

Перед слиянием pull request проверьте:

- изменения wire format, crypto и handshake;
- изменения YAML schema и обязательных полей;
- изменения CLI и имен выходных бинарников;
- совместимость Go version с GitHub Actions;
- сборку `linux/amd64` и `linux/arm64`;
- тесты Debian и Keenetic packaging;
- необходимость одновременного обновления VPS и роутера.

## Ручная синхронизация

Если GitHub Actions недоступен:

```sh
git switch master
git pull --ff-only origin master
git fetch upstream master
git switch -c sync/upstream-YYYYMMDD
git merge --no-ff upstream/master
printf '%s\n' "$(git rev-parse upstream/master)" > packaging/release/UPSTREAM_COMMIT
git add packaging/release/UPSTREAM_COMMIT
git commit -m "chore: record upstream commit"
mage check
sh packaging/release/test-assemble-assets.sh
git push -u origin sync/upstream-YYYYMMDD
```

После этого откройте pull request в `master`. Не публикуйте релиз из временной ветки.

## Релиз

Workflow `Fork release` запускается только вручную. По умолчанию релиз помечается как prerelease. Workflow разрешает выпуск только из текущего HEAD основной ветки.

Перед сборкой выполняются:

- `mage check`;
- `golangci-lint` зафиксированной версии;
- ShellCheck для файлов упаковки;
- тест сборки и строгой структуры manifest;
- необязательный real-provider E2E, если его включили при запуске.

После проверок `mage cross` собирает все upstream targets из одного checkout. В релиз попадают два raw-бинарника:

- `olcrtc-linux-amd64` для Debian VPS;
- `olcrtc-linux-arm64` для Keenetic/Entware.

Оба файла соответствуют одному `source_commit`. Платформенные скрипты поставляются отдельными архивами:

- `olcrtc-debian-amd64.tar.gz`;
- `olcrtc-keenetic-arm64.tar.gz`.

## Формат manifest.tsv

`manifest.tsv` использует UTF-8, LF и табуляцию как разделитель. Фиксированные строки содержат два поля:

```text
manifest_version<TAB>1
version<TAB>v0.1.0
wire<TAB>OLC2-OLVC5
config_schema<TAB>1
source_repository<TAB>qqweqwe287-art/olcrtc
source_commit<TAB>40-hex
upstream_repository<TAB>openlibrecommunity/olcrtc
upstream_commit<TAB>40-hex
go_version<TAB>go1.26.3
```

Каждый asset описывается ровно семью полями:

```text
asset<TAB>core|bundle<TAB>linux<TAB>amd64|arm64<TAB>filename<TAB>size<TAB>sha256
```

Manifest версии 1 содержит ровно четыре asset:

- `core linux amd64`;
- `core linux arm64`;
- `bundle linux amd64` для Debian;
- `bundle linux arm64` для Keenetic.

Имена файлов являются basename без URL, абсолютных путей, `..` и разделителей каталогов. Установщики обязаны:

1. Скачать `manifest.tsv` по HTTPS из выбранного GitHub Release.
2. Разобрать только известные строки с точным числом полей.
3. Отклонить дубли, неизвестные обязательные значения и неправильную архитектуру.
4. Проверить числовой размер файла.
5. Проверить SHA-256 до распаковки или запуска.
6. Не выполнять manifest через `source`, `.`, `eval` или командную подстановку.

`SHA256SUMS` покрывает оба бинарника, оба bundle и сам `manifest.tsv`. Контрольная сумма выявляет повреждение, но не заменяет криптографическую подпись издателя. Workflow не заявляет наличие подписи, пока отдельный signing secret и процедура проверки не настроены.

## Совместимость обновлений

Текущий wire marker равен `OLC2-OLVC5`. Если upstream меняет record layer, frame version, handshake или обязательную YAML schema, нужно:

1. Обновить marker и номер schema только после анализа исходников и тестов.
2. Выпустить серверный и клиентский бинарники вместе.
3. Сначала сохранить рабочий предыдущий релиз для rollback.
4. Обновить VPS и Keenetic в согласованном окне.
5. Проверить SOCKS-туннель до включения маршрутизации LAN.

Нельзя смешивать бинарники разных релизов только потому, что они запускаются без ошибки. Несовместимость может проявиться после WebRTC handshake или при первом трафике.

## Проверка скачанного релиза

На системе с GNU coreutils:

```sh
sha256sum -c SHA256SUMS
```

Дополнительно сравните `source_commit` в `manifest.tsv` с commit страницы GitHub Release. Для обновления двух сторон используйте один и тот же тег.

## Rollback

Установщики должны заменять бинарник атомарно и сохранять предыдущую рабочую версию. Если новая версия не проходит запуск, проверку SOCKS или проверку маршрутов, установщик возвращает предыдущий бинарник и конфигурацию. Ошибка обновления одной стороны не является разрешением автоматически обновлять вторую сторону.
