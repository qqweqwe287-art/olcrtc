# Установка сервера olcRTC на Debian 12

Эта упаковка устанавливает официальный Go-бинарник olcRTC как непривилегированную systemd-службу и отдельную HTTPS-панель управления. Новый пакет использует namespace `olcrtc-native`. В обычном режиме он не заменяет старый Manager, а в режиме `--fresh` сначала создаёт recoverable backup, проверяет запуск новой панели и только затем удаляет точный allowlist старых файлов.

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

Если нужно полностью заменить уже установленный старый Manager:

```sh
/tmp/install-server.sh --fresh
```

Старые службы останавливаются только после загрузки и проверки нового release. Если новая панель не запускается, установщик возвращает старые службы. Копия сохраняется в `/var/backups/olcrtc-native/legacy-manager-<UTC>`.

После установки откройте `https://IP_СЕРВЕРА:8443`. Сертификат при первой установке самоподписанный, поэтому браузер покажет предупреждение. Логин и одноразовый пароль находятся в `/root/olcrtc-native-admin.txt`. Удалите этот файл после сохранения пароля.

Панель создаёт, клонирует и удаляет инстансы, управляет DNS, liveness, lifecycle, traffic и transport-параметрами, формирует конфигурации и ключи, запускает службы, показывает журналы и скачиваемую диагностику, формирует Spec URI и QR, а также устанавливает обновления. Transport-параметры включаются в URI для клиента. Перед изменением и удалением создаётся root-only backup с SHA-256; его можно восстановить из панели. Без `--start` placeholder-конфиг не запускается автоматически.

## Конфигурация

Скопируйте пример и создайте отдельный ключ:

```sh
install -o root -g olcrtc-native -m 0640 \
  /etc/olcrtc-native/server.example.yaml /etc/olcrtc-native/main.yaml
openssl rand -hex 32 | install -o root -g olcrtc-native -m 0640 \
  /dev/stdin /etc/olcrtc-native/main.key
```

Откройте `/etc/olcrtc-native/main.yaml` и замените полный URL комнаты Jitsi. Значение должно иметь вид `https://host.example/room-name`. `any` и URL без комнаты недопустимы.

Клиенту нужны тот же release tag, provider, transport, room и ключ. Ключ не публикуйте.

Запуск:

```sh
systemctl enable --now olcrtc-native@main.service
systemctl status olcrtc-native@main.service
journalctl -u olcrtc-native@main.service -f
```

Проверка статуса systemd подтверждает только состояние серверного процесса. Сквозную работу туннеля проверяют через SOCKS5 на клиентской стороне.

## Установка готового YAML

Можно передать существующий конфиг сразу:

```sh
/tmp/install-server.sh --config /root/server.yaml --start
```

Существующий `/etc/olcrtc-native/main.yaml` не заменяется. Для осознанной замены нужен флаг `--replace-config`.

Для второго сервера используйте другой instance:

```sh
/tmp/install-server.sh --instance backup --config /root/backup.yaml --start
```

Он запустится как `olcrtc-native@backup.service` с конфигом `/etc/olcrtc-native/backup.yaml`.

## Обновление и rollback

Повторный запуск установщика выполняет обновление. Активные olcRTC-инстансы перезапускаются с новым бинарником. Файлы конфигурации без `--config --replace-config` не изменяются.

```sh
/tmp/install-server.sh --release '<exact-tag>'
```

Каждый бинарник хранится в `/usr/local/lib/olcrtc-native/releases/<tag>`. Ссылка `current` меняется атомарно. Если активный unit не может запуститься после замены, установщик возвращает предыдущую ссылку и unit, затем пытается перезапустить старую версию.

Проверьте версию пары по manifest:

```sh
sed -n -e '/^version\t/p' -e '/^upstream_commit\t/p' \
  /usr/local/lib/olcrtc-native/current/manifest.tsv
```

## Удаление

Удалить программу и сохранить конфиги/state:

```sh
/usr/local/sbin/olcrtc-native-uninstall-server
```

Полностью удалить также `/etc/olcrtc-native`, `/var/lib/olcrtc-native` и service account:

```sh
/usr/local/sbin/olcrtc-native-uninstall-server --purge
```

`--purge` необратим. Перед ним сохраните YAML и ключи в безопасном месте.

## Системные пути

```text
/usr/local/lib/olcrtc-native/releases/<tag>/olcrtc
/usr/local/lib/olcrtc-native/current
/usr/local/bin/olcrtc-native
/etc/olcrtc-native/<instance>.yaml
/etc/olcrtc-native/<instance>.key
/var/lib/olcrtc-native/<instance>/
/etc/systemd/system/olcrtc-native@.service
/etc/systemd/system/olcrtc-native-admin.service
```

Сервер работает от пользователя `olcrtc-native`, не имеет Linux capabilities и получает только сетевые семейства `AF_INET`, `AF_INET6`, `AF_UNIX`. Журналы находятся в systemd journal. Секретные файлы не должны иметь права шире `0640`.
