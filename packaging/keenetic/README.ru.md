# olcRTC для Keenetic Entware

<!-- ai-generated: generic installation and recovery guide for the Keenetic package. -->

Эта упаковка запускает официальный клиент olcRTC на Keenetic с Entware. Поддерживается `aarch64/arm64`, локальный SOCKS5 `127.0.0.1:8808`, автозапуск, безопасное обновление и веб-панель в домашней сети.

Первая версия намеренно не создаёт TUN, не меняет маршруты Keenetic и не открывает порты на WAN. Сначала проверяется отдельный SOCKS5. Маршрутизация всей сети должна быть отдельным, явно включаемым этапом.

## Требования

- Keenetic с установленным и работающим Entware в `/opt`;
- архитектура `aarch64/arm64`;
- доступ к GitHub по HTTPS и корректное время на роутере;
- Spec URI из совместимого серверного релиза.

Сервер и клиент должны использовать один GitHub Release. Manifest фиксирует `source_commit`, wire `OLC2-OLVC5`, размеры и SHA-256 обоих бинарников.

## Установка одной командой

Войдите по SSH как `root`, сохраните raw-скрипт и запустите его:

```sh
curl -fL --proto '=https' --tlsv1.2 \
  -o /opt/tmp/olcrtc-bootstrap.sh \
  https://raw.githubusercontent.com/qqweqwe287-art/olcrtc/master/packaging/keenetic/bootstrap.sh \
  && chmod 700 /opt/tmp/olcrtc-bootstrap.sh \
  && /opt/tmp/olcrtc-bootstrap.sh
```

Установщик попросит вставить raw `olcrtc://...` URI. Не вставляйте Markdown вида `[https://...](https://...)`, HTML или URL страницы панели. Для Jitsi URI обязан содержать полный адрес комнаты, например `https://meet.example.org/room-name`. Значение `any` недопустимо.

Для PuTTY вставка обычно выполняется правой кнопкой мыши или `Shift+Insert`. Ввод URI скрыт, поэтому символы на экране не появляются. После вставки нажмите Enter.

Без интерактивной вставки:

```sh
umask 077
vi /opt/tmp/spec-uri.txt
/opt/tmp/olcrtc-bootstrap.sh --uri-file /opt/tmp/spec-uri.txt
rm -f /opt/tmp/spec-uri.txt
```

## Веб-панель

При первой установке создаётся случайный пароль. Он показывается один раз в конце установки. Логин: `admin`.

Если интерфейс `br0` имеет IPv4-адрес, панель привязывается только к этому адресу на порту `8091`. Иначе она остаётся на `127.0.0.1:8091`. Wildcard-адреса `0.0.0.0` и `::` запрещены. Доступ с WAN не настраивается.

Команды панели:

- состояние supervisor, дочернего процесса и SOCKS5;
- запуск, остановка и перезапуск;
- сквозной SOCKS5-тест;
- импорт нового Spec URI;
- журнал с удалением распространённых форм секретов.

Панель работает от `root`, потому что управляет init-службой. Она принимает только фиксированный набор команд без shell, проверяет пароль, сессию, CSRF и Origin. Не публикуйте порт панели в интернет.

## Проверка

Подождите до 30 секунд:

```sh
/opt/etc/init.d/S98olcrtc-client status
/opt/lib/olcrtc-keenetic/doctor.sh --quick
curl --socks5-hostname 127.0.0.1:8808 https://icanhazip.com
```

Третий вызов должен вернуть публичный IP VPS. Если порт не слушает:

```sh
/opt/etc/init.d/S98olcrtc-client log 120
/opt/lib/olcrtc-keenetic/doctor.sh
```

Частые причины:

- `data directory required`: смешаны старый конфиг и несовместимый бинарник;
- `invalid room URL` или `room=any`: в Spec URI нет настоящего Jitsi URL с комнатой;
- `unsupported provider/transport`: выбрана заведомо нерабочая пара;
- checksum/size mismatch: выпуск повреждён или изменился во время загрузки;
- repeated early exits: supervisor остановил цикл после пяти быстрых падений.

В текущем upstream рекомендуется `jitsi + datachannel`. Для WB Stream применяется `wbstream + vp8channel`; `wbstream + datachannel` отклоняется заранее.

## Обновление и rollback

```sh
/opt/lib/olcrtc-keenetic/upgrade.sh
```

Обновление загружает manifest по сохранённому HTTPS URL, проверяет строгую схему, repository, архитектуру, размер и SHA-256. Новый бинарник считается рабочим только после запуска дочернего процесса и проверки SOCKS-порта. При ошибке восстанавливаются предыдущий бинарник, release metadata и URL manifest.

`--no-start` устанавливает проверенный бинарник, но оставляет клиент остановленным. Конфиг и ключи при обычном обновлении не заменяются.

## Ручное управление

```sh
/opt/etc/init.d/S98olcrtc-client start
/opt/etc/init.d/S98olcrtc-client stop
/opt/etc/init.d/S98olcrtc-client restart
/opt/etc/init.d/S98olcrtc-client status
/opt/etc/init.d/S97olcrtc-web status
```

Импорт нового URI:

```sh
/opt/lib/olcrtc-keenetic/import-uri.sh
/opt/etc/init.d/S98olcrtc-client restart
```

## Удаление

Сохранить конфиг и state:

```sh
/opt/lib/olcrtc-keenetic/uninstall.sh
```

Удалить также конфиг, ключи и state:

```sh
/opt/lib/olcrtc-keenetic/uninstall.sh --purge
```

`--purge` необратим. Зависимости Entware не удаляются.

## Границы первой версии

- только Keenetic Entware ARM64;
- только SOCKS5 на loopback;
- без автоматического TUN, policy routing, NAT и DNS hijack;
- без доступа к веб-панели через WAN;
- checksum не заменяет криптографическую подпись издателя.

Такой порядок позволяет проверить туннель, не рискуя потерять интернет или доступ к роутеру.
