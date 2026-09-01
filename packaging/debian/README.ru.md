# Установка сервера olcRTC на Debian 12

Эта упаковка устанавливает официальный Go-бинарник olcRTC как непривилегированную systemd-службу. Она не содержит веб-панель и не изменяет маршруты сервера.

Первая версия упаковки поддерживает Debian 12 `amd64`. Бинарник `arm64` может присутствовать в выпуске для других платформ, но Debian bundle для `arm64` в manifest v1 пока не публикуется. Установщик явно остановится на такой системе.

## Модель выпуска

Один GitHub Release содержит:

- `manifest.tsv`;
- raw-бинарники `olcrtc-linux-amd64` и `olcrtc-linux-arm64`;
- `olcrtc-debian-amd64.tar.gz`;
- отдельный Keenetic bundle.

`manifest.tsv` связывает все файлы с одним tag, commit форка и commit официального upstream. Для каждого asset записаны размер и SHA-256. Установщик сначала разрешает `latest` в точный tag, затем повторно загружает manifest по этому tag. Сервер и клиент следует устанавливать из одного tag.

Проверка SHA-256 защищает от повреждения файла, но сама по себе не заменяет подпись manifest. Для строгого bootstrap передайте опубликованную отдельно сумму:

```sh
OLCRTC_MANIFEST_SHA256='<64 hex>' ./install-server.sh --release '<tag>'
```

Скрипт никогда не выполняет `source manifest.tsv`. Парсер принимает только известные строки с точным числом TAB-полей.

## Быстрая установка

Запускайте от `root`. Если вы вошли как `root`, `sudo` не нужен.

```sh
curl -fL -o /tmp/install-server.sh \
  https://raw.githubusercontent.com/qqweqwe287-art/olcrtc/master/packaging/debian/install-server.sh
chmod 0755 /tmp/install-server.sh
/tmp/install-server.sh
```

Без `--start` программа только устанавливает бинарник, unit и пример конфигурации. Placeholder-конфиг никогда не запускается автоматически.

## Конфигурация

Скопируйте пример и создайте отдельный ключ:

```sh
install -o root -g olcrtc -m 0640 \
  /etc/olcrtc/server.example.yaml /etc/olcrtc/main.yaml
openssl rand -hex 32 | install -o root -g olcrtc -m 0640 \
  /dev/stdin /etc/olcrtc/main.key
```

Откройте `/etc/olcrtc/main.yaml` и замените полный URL комнаты Jitsi. Значение должно иметь вид `https://host.example/room-name`. `any` и URL без комнаты недопустимы.

Клиенту нужны тот же release tag, provider, transport, room и ключ. Ключ не публикуйте.

Запуск:

```sh
systemctl enable --now olcrtc-server@main.service
systemctl status olcrtc-server@main.service
journalctl -u olcrtc-server@main.service -f
```

Проверка статуса systemd подтверждает только состояние серверного процесса. Сквозную работу туннеля проверяют через SOCKS5 на клиентской стороне.

## Установка готового YAML

Можно передать существующий конфиг сразу:

```sh
/tmp/install-server.sh --config /root/server.yaml --start
```

Существующий `/etc/olcrtc/main.yaml` не заменяется. Для осознанной замены нужен флаг `--replace-config`.

Для второго сервера используйте другой instance:

```sh
/tmp/install-server.sh --instance backup --config /root/backup.yaml --start
```

Он запустится как `olcrtc-server@backup.service` с конфигом `/etc/olcrtc/backup.yaml`.

## Обновление и rollback

Повторный запуск установщика выполняет обновление. Активные olcRTC-инстансы перезапускаются с новым бинарником. Файлы конфигурации без `--config --replace-config` не изменяются.

```sh
/tmp/install-server.sh --release '<exact-tag>'
```

Каждый бинарник хранится в `/usr/local/lib/olcrtc/releases/<tag>`. Ссылка `current` меняется атомарно. Если активный unit не может запуститься после замены, установщик возвращает предыдущую ссылку и unit, затем пытается перезапустить старую версию.

Проверьте версию пары по manifest:

```sh
sed -n -e '/^version\t/p' -e '/^upstream_commit\t/p' \
  /usr/local/lib/olcrtc/current/manifest.tsv
```

## Удаление

Удалить программу и сохранить конфиги/state:

```sh
/usr/local/sbin/olcrtc-uninstall-server
```

Полностью удалить также `/etc/olcrtc`, `/var/lib/olcrtc` и service account:

```sh
/usr/local/sbin/olcrtc-uninstall-server --purge
```

`--purge` необратим. Перед ним сохраните YAML и ключи в безопасном месте.

## Системные пути

```text
/usr/local/lib/olcrtc/releases/<tag>/olcrtc
/usr/local/lib/olcrtc/current
/usr/local/bin/olcrtc
/etc/olcrtc/<instance>.yaml
/etc/olcrtc/<instance>.key
/var/lib/olcrtc/<instance>/
/etc/systemd/system/olcrtc-server@.service
```

Сервис работает от пользователя `olcrtc`, не имеет Linux capabilities и получает только сетевые семейства `AF_INET`, `AF_INET6`, `AF_UNIX`. Журналы находятся в systemd journal. Секретные файлы не должны иметь права шире `0640`.
