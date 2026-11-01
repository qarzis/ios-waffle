> Current update: E21 verified eight compute shader results (0–7) and all 4,096 buffer words under XNU. E19/E20 verified AOP lifetime and post-startup BO access. Images and the iOS GPU backend remain unfinished. This document retains its earlier audit inventory; see [E21-result.json](E21-result.json) for the newer hardware result.

## Обновление после E09–E11-r2: CP, ZAP, DMA и IB подтверждены

E09 аппаратно подтвердил signed ZAP/PAS13 authentication, native secure-switch
ACK0 и TRUST0. E10 подтвердил прямую запись GPU с фактическим чтением CPU.
E11-r2 подтвердил чтение PM4 из GPU-памяти через IB и выполнение записи;
все4096слов (включая команды и guards) проверены, wrong0. Полная остановка и
Android подтверждены после каждого теста; 900e не было.

Первый E11 завершился точным permission fault FSR408, FAR=адресIB,
непривилегированное чтение. Он выявил ошибку нового диагностического BO:
не был установлен AP_UNPRIV. Исправление только этого BO устранило отказ;
пакеты и GMU код сохранены неизменными. Это не новый вывод о старом CP94
до исправления LPAC, а отдельный доказанный дефект вновь добавленного IB-теста.

Следующий блокер — отсутствие постоянного waffle backend с владением ресурсами,
BO/VA/submit/fence и проверенным остановом. Существующий RedwoodGPU/Mesa
транспорт применим, но ещё не подключён к работающему waffle backend.
Рисование, shader execution, кадры и GPU-композиция iOS пока не проверены.
См. IOS-GPU-INTEGRATION.md, E09-result/E10-result/E11-result/E11-r2-result.json.
Ниже сохранены исторические этапы аудита.

## Обновление после E08: прежний блокер CP_INIT пройден

31 октября 2026: два запуска неизменного образа — 20261031T100500Z и
20261031T100701Z — получили CP_INIT_RAW seq42 ACK0 valid1, Gen7result0,
полный shutdown/PLL restore и подтверждённый Android. E07 предварительно
проверил42 перевода SQE через отсутствовавший SID1. Добавлены LPAC SID1/CB1,
его native SCM aperture, native GMU SID5/CB3 и TLBI обоих ASID при общих
изменениях таблиц. Эти предпосылки вместе устраняют прежний сбой CP_INIT;
отдельный вклад каждого изменения и конкретный исторический fault не декодированы.
Нет900e в этих двух запусках. Это подтверждает инициализацию CP, но не кадры.

| Компонент | Текущее подтверждение |
|---|---|
| Питание, clocks, GMU/HFI | Проверены запуск и полный останов; физические GFX~231/GMU~260МГц |
| IOMMU user/protected/LPAC/GMU | Проверены diagnostic translations и teardown; произвольный DMA пока не проверен |
| Command submission | Частично: полная штатная CP_INIT аппаратно подтверждена дважды |
| Synchronization | ACK/idle поллятся; пользовательские fences и GPU writeback не проверены |
| ZAP/PAS13 и unsecure transition | Отсутствует runtime implementation; есть firmware и offline parser |
| Рисование и Mesa backend waffle | GPU draw не проверен; полноценный backend не реализован |
| Графический стек iOS | Существующий программный вывод работает; GPU integration не подтверждена |

Текущая следующая граница: native authenticated ZAP load/unsecure transition
и независимый результат GPU memorywriteback. До записи в reserved ZAP region
нужно подтвердить владение RAM, PAS ABI и map/cache lifetime по исходникам.
GPU_DEBUG_LOG.md и E08-result.json/E08-repeat-result.json содержат результаты.
Ниже сохранён исходный аудит до этих экспериментов.

# Аудит GPU OnePlus 12, 31 октября 2026

## Блокер и границы доказанного

Не подтверждено исполнение CP_INIT на Adreno 750 под XNU. Подготовительный тест №93 прошёл; №94 с полным RAW CP_INIT завершился потерей USB и аварийным режимом 900e. Android восстановлен, что записано в `diagnostic-gpu-native94/hardware-result-94.json`. Причина аппаратного сброса пока **не установлена**.

Проверены все 88 сохранённых `kernel-*.log` из `runs/20261031T074659Z`: присутствуют checkpoint 0–3, нет сохранённой checkpoint 4 и RAW ACK. Последняя строка: `RAW_EDGE68 staged hold 5s; index unpublished`. До неё получены ACK START, MINIMUM_DCVS и NATIVE_DDR_AB. Это локализует последний наблюдаемый участок, но не доказывает, что публикация или уведомление не выполнялись: запись следующего сообщения тоже требует работающего CPU и логирования.

Повторяемая проверка: `python3 work/waffle/gpu/forensic-audit/verify_evidence.py`. Результаты: `test94-boundary.json`, `raw-packet-comparison.json`, `source93-vs94.diff`, `freeze-verification.json`. 31 замороженный исходный файл остался неизменным. Скрипт не обращается к телефону.

## Что уже проверяли

Хронология восстановлена по `RESUME.md`, `docs/waffle-gpu.md`, структурированным hardware-result, исходникам диагностических сборок и сохранённым трассам. Номера диагностик не равны числу независимых опытов: есть повторные сборки, отказы до выполнения и дубликаты отчётов. Машинный список содержит 65 отчётов; сводка в `HISTORY.md`. Старые записи в RESUME сохраняются как история, а не как действующая инструкция запускать тест.

| Период / проверки | Изменение и наблюдение | Что из этого следует |
| --- | --- | --- |
| 24 октября, 1–9 | Шины, CX, clocks, QTB, таблицы, загрузка и запуск GMU по шагам; сначала ошибка восстановления CBAR, затем исправленные 7–9 прошли | Работают базовые диагностические операции и отдельный путь GMU; исполнения CP это не доказывает |
| 10–20 | HFI, firmware tables/features, SCM aperture, OOB GX и выключение | Есть связь с GMU и управляемый цикл питания |
| 21–23 | Прямой CPU-путь включения SQE / ring; аварийные результаты, включая enable-only | Прямой ring не стал рабочим CP; обход HWSCHED не является готовым решением |
| 24–32 | Переход к HWSCHED, START memory allocation, защищённая память, setup/HWCG/restore | Подготовительные проверки проходят; CPU readback не равен GPU DMA |
| 33–40 | Полный RAW, SCM aperture, высокие GPU VA | Подготовительные контроли проходят, RAW не получает ACK; наличие SCM или высокого VA не устранило сбой |
| 41–53 | DMS capability, BCL, AOP/ACD, bailout, живое сохранение конфигурации | Проходящие контроли и падающие RAW; эти настройки по отдельности недостаточны |
| 54–57 | Исправлено пересечение compact aliases с GMU firmware, затем native trusted window / secure VA | Исправленные контроли 54/56 проходят; 55/57 RAW падают |
| 58–62 | RAM manifest/export, restore-list и LLCC аудит | Есть дополнительные снимки; чтение произвольной DDR через непредусмотренный Sahara запрос не заработало; полного decoded reset reason нет |
| 63–70 | Native optional-off profile, ACD-first, staging-only 67, edge logging 68, ACD event 69 | 63/65/67/69 проходят; RAW 64/66/68/70 падают. 67 не публикует индекс |
| 71–76 | Thread-only, AP permissions HFI allocations, query-after-prepare, native DDR votes | Права исправлены; минимальный thread RAW всё равно падает. Обычные запросы HFI после настройки GPU работают |
| 77–80 | 10 s timer control, состояние CP, монотонные sequence | Контроли проходят; thread RAW 80 падает. Простой таймаут и только порядок sequence не объясняют весь сбой |
| 81–86 | Исправлен TG1, HUPCF; затем полный 11-word CP_INIT | Контроли 81/83/84 проходят; 82/85/86 падают. TG1 — реальный исправленный дефект, но не достаточное исправление текущего блокера |
| 87–91 | PLL readback, GMU 200 MHz, stall на protected CB2 | Контроли 87/88/90 проходят, полные RAW 89/91 падают |
| 92–94 | Изолированное PLL1 1250→520 и восстановление; GMU 625→260 с NPA hold | 92/93 проходят, полный RAW 94 падает. Профиль clock lifecycle работоспособен без CP; полная исправность питания под CP не доказана |

Первая документированная причинно объяснённая аппаратная ошибка раннего bring-up — восстановление сброшенного CBAR type0: это запрос unsupported stage2 при IDR0.S2TS=0. Исправленный stage7 прошёл дважды. Основание: `docs/waffle-gpu.md` около строки 164; первичный panic здесь повторно не декодирован. **Это историческая причина раннего сбоя, не объяснение нынешнего 900e.**

Другие доказанные дефекты: пересечение compact mappings и TG1=0 вместо TG1=2 для TTBR1 4K. Исправление последнего отдельно выявило ошибку методики: прежний host test повторял неверную константу порта и тоже проходил. Ни один из этих фиксов не обеспечил CP ACK.

## Источники, зависимости и история

- Базовый Git commit `c0ec663`, 22 октября: донор OnePlus Ace 6T / Adreno 829 (Gen8). Отдельных GPU-коммитов предыдущих шагов в текущей истории нет. Большая часть waffle GPU-файлов была untracked; изменения нельзя честно восстановить только через git log.
- Портируемый GPU: Adreno 750 / Gen7.9.1, chipid `0x43051401`, SM8650. Регистры и firmware Gen8 нельзя переносить без сопоставления.
- Native KGSL / DT: OnePlus modules commit `c951f93ec63fbee49d468ee2f9d93ac0e807da67`; kernel reference `e39bf7032e38c547d588372a11a5dd55eb714860`. Локальные provenance-файлы содержат URL и SHA256.
- Прямые зависимости порта: `waffle_adreno.c`, `waffle_gmu.c`, `waffle_smmu.c`, `waffle_*` GPU headers, loader power/memory handoff, packfs firmware, `loader_return.c`, `kernel.patch`, build/runner/validation scripts.
- Firmware GMU/SQE/AQE — vendor binaries. Наличие совпадающих полных CPU-хешей SQE/AQE проверялось, см. `native-ucode-full-audit.json`; оно не доказывает GPU fetch. Исходников GMU/SQE/AQE firmware в доступном наборе нет.
- Runtime и snapshot sources сравниваются отдельно: найдено 12 отличающихся файлов между source snapshots 93/94. Большая часть изменений включает допуск №94 и ветку RAW; поэтому «единственное изменение — doorbell» слишком сильное описание пары. Полный diff сохранён для проверки.

Проверена цепочка GPU bring-up, SMMU/SCM, HFI/CP, связанные заголовки и маршрутизация iOS. Это не утверждение о построчном аудите всех исходников XNU, Mesa и всего дерева vendor. История ранних 1–32 частично опирается на журнал, а не на полный набор однотипных hardware-result.

## Architecture gap analysis

Здесь «реализован» означает наличие соответствующего пути; это не автоматическое подтверждение GPU-рендеринга.

| Компонент | Статус | Связь с XNU и доступное доказательство / пробел |
| --- | --- | --- |
| Hardware profile / MMIO | Реализован | DT-профиль Gen7, `ml_io_map`, volatile accesses и barriers; прошедшие подготовительные аппаратные проверки |
| CX/GX, clocks, resets | Частично реализован | Диагностический контролируемый цикл, NPA handoff, GMU PLL1 ownership; 93 прошёл. Нет production power management с GPU нагрузкой |
| GMU firmware boot | Реализован | Packfs, kmem, загрузка TCM/regions, FW_INIT и HFI ответы; закрытая firmware не аудирована изнутри |
| SQE/AQE firmware | Частично реализован | CPU copy/hash/clean, GPU VA и base registers; исполнение / fetch не проверены |
| SCM / secure allocation | Частично реализован | Native aperture SCM уже вызывается; MP_ASSIGN, отдельные protected pages/table ownership. Контроли проходят; исполнение secure CP не доказано |
| ZAP и выход из trusted mode | Частично реализован | Есть offline parser, runtime PAS/ZAP load и unsecure transition отсутствуют. Native HWSCHED сначала делает cp_init, потом ZAP; отсутствие ZAP само по себе не доказанная причина первого RAW |
| SMMU / IOMMU | Частично реализован | Таблицы 4K поверх страниц XNU 16K, TTBR split, TG1 fix, AP, TLBI, ECATS. Совпадение необходимых реальных GPU access modes ещё не проверено |
| DMA / coherency | Не проверен для CP | Есть PA checks, cache clean/invalidate, NC mappings и dsb; нет измеренного CP read/write результата из GPU memory |
| IRQ / faults | Частично реализован | IRQ status polling есть. XNU handlers GPU/GMU/SMMU не подключены; fault capture после RAW зависит от выживания CPU. Native host mask содержит error IRQ, поэтому обещать исправление RAW одним completion IRQ нельзя |
| HFI queues и START | Реализован | Очереди, padding/wrap, ACK correlation, allocation replies; START и post-prepare query проходят |
| HFI memory contract | Частично реализован | Normal/protected pools, flags/AP, aliases, reserve/reuse. Не полный аналог KGSL memory subsystem; runtime backing-data / access semantics требуют проверки |
| CP init / command submission | Частично реализован | Есть RAW packet и bounded poll, а также старый прямой ring путь; успешного ACK/idle исполнения нет |
| Synchronization / fences | Отсутствует для waffle workloads | Диагностическое ожидание HFI не является BO fence, timestamp или пользовательской очередью |
| Production BO / VM / recovery | Отсутствует для waffle backend | Нет подключённого waffle backend allocation/submission/context lifetime и reset recovery для приложений |
| IOService / IOUserClient bridge | Частично реализован в доноре | `MacanGPU.cpp` существует, требует `redwood_gpu_ready()` и вызывает donor backend. waffle init не подключает этот путь |
| IOSurface / display presentation | Частично реализован в доноре | Есть donor bridge; рендеринг и передача GPU-кадра от waffle не проверены |
| Mesa / OpenGL ES / CoreAnimation | Частично реализован | Mesa узнаёт FD750; `inject.c` для waffle явно включает `GALLIUM_DRIVER=softpipe`. UI сейчас рендерится CPU |
| Metal | Отсутствует | Подключённого Metal backend / translation для этого GPU нет |

Ключевые местные свидетельства: `macan_input.c:175` выбирает waffle init отдельно от donor GPU; `inject.c:736` принудительно включает softpipe; `MacanGPU.cpp:344` требует donor ready. Поэтому даже успешный CP_INIT не завершит порт iOS graphics stack.

## Максимум три гипотезы текущего блокера

Это гипотезы, а не установленные причины. Прямого fault address / decoded reset reason нет, поэтому ранжирование предварительное.

| ID | Гипотеза | Основание и проверка | Предсказание / критерий отказа |
| --- | --- | --- | --- |
| H1, приоритет | Нужный тип GPU-доступа отвергается SMMU, хотя privileged data-read ECATS проходит | В порте `translate_page` всегда INFLD0=sid, INFLD1=0x2408. Native поддерживает отдельные PRIV/INST/WRITE/SEC параметры. Исторически уже были ошибки TG1/AP. Проверить адреса SQE/AQE, restore и HFI allocations с требуемыми типами доступа, без RAW | Для конкретного доступа появляется fault или неверный PA → локализован нарушенный access contract. Все необходимые режимы проходят → отвергнуть узкую гипотезу о разрешениях/трансляции для проверенных адресов. Это не доказательство actual DMA/coherency |
| H2 | Условия старта GX/CP отличаются от native несмотря на успешную подготовку | Успех query не включает CP execution; разные clock profiles не помогли, не все runtime prerequisites наблюдаемы. Сопоставить native cold pre-CP состояние и порядок операций с портом, только при конкретном новом отличии делать одну правку | Нужен новый конкретный prerequisite и воспроизводимая смена результата. Без отличия не повторять PLL/ACD/SCM/trusted-window опыты |
| H3 | Сбой возникает в RAW publication / firmware handling, а сохранённый лог не успевает указать фазу | 67 staging и 77 delay отдельно прошли, обычные HFI запросы работают. Не хватает наблюдения после publish, hardware reset может прерывать host log. Нужен переживающий сброс маркер фаз или достоверный native reset/fault record | Сохранённый индекс/фаза отделяет prepublication от consumed RAW. Без сохраняемого состояния очередное добавление printf не является различающим экспериментом |

Содержимое пакета не выделено в новую гипотезу: независимая сверка уже дала 0 несовпадений в 10 native CP_INIT записях, если нормализовать только sequence и restore VA. Нельзя объявлять повторение этой сверки новой GPU-вехой.

## Первый выбранный эксперимент и сделанная подготовка

Выбран H1 как ближайший непроверенный контракт, для которого есть native encoding и ограниченный тест без CP. Начальная offline-проверка установила **слепую зону прежнего ECATS теста**, но не подтвердила H1 как причину 900e: существующие 0x2408 не проверяют INST, WRITE или unprivileged access.

Следующий аппаратный эксперимент: тот же подтверждённый prepare-only цикл, без CP RAW, с ограниченной матрицей ECATS для первых/последних страниц SQE/AQE (unprivileged instruction read), restore (privileged data read/write) и реальных START allocations по их flags. Точные SID и контексты должны браться из действующего native/port routing; не подменять их произвольными stream IDs. Для каждого запроса сохранить VA, режим, expected/actual PA и FSR/FAR. При первом отличии остановить матрицу и выполнить предусмотренный shutdown; неопределённое владение памятью требует reset, а не освобождения страниц.

Условия измеримого результата: (1) конкретный режим+адрес с fault/mismatch либо (2) все запрошенные режимы прошли, и H1 в этом объёме отвергнута. Никакого заявления об actual DMA только на основании ECATS. Secure tests и actual GPU readback — отдельные последующие вопросы.

Пока телефон не нужен и исходники не изменялись. Матрица ещё не реализована и не запущена: сначала требуется закончить точное сопоставление access types с native metadata. Разбор public source не раскрывает внутренний transaction type закрытого SQE; выбранный INST режим — дополнительная проверка, не утверждение, что микрокод всегда грузится именно instruction transaction.

Дополнительно исследован native crashdumper как возможный независимый DMA readback: `reference/adreno_gen7_snapshot.c` с pinned URL/SHA256. Он использует **GPU VA**, а не физические адреса, и запускается в snapshot path; источник не доказывает работоспособность до CP init. Поэтому он не принят за готовый безопасный обход текущего блокера.

## Что требуется дальше и чего не хватает

Нет исходников закрытой GMU/SQE/AQE firmware, декодированного reset reason / postpublication fault и аппаратного доступа в текущем offline этапе. Firmware binaries, native kernel sources и saved traces доступны. Недостающие данные не заменяются догадкой о причине 900e.

Порядок следующих независимо проверяемых вех: (1) подтвердить нужные memory access contracts; (2) один CP command с ACK и отдельным memory result; (3) bounded fence/timestamp; (4) ZAP/unsecure transition в native порядке; (5) один offscreen draw с проверкой пикселей; (6) waffle BO/VM/submit/fence backend для IOUserClient; (7) Mesa/EGL/IOSurface presentation; (8) CoreAnimation GPU path. Metal — отдельная задача.

После каждого будущего source change — scoped diff, доступная сборка и релевантная проверка; после hardware check — фактические результаты и recovery. После трёх безрезультатных аппаратных опытов — остановка аппаратной итерации и пересмотр архитектуры. Старые отрицательные результаты сохраняются. Текущее состояние сохраняется отдельным Git snapshot без переключения рабочей ветки и без публикации.

## Обновление после E03/E04

E03 аппаратно прошёл: 27 ECATS проверок, восемь HFI allocations, отсутствие fault bits и совпадение PA, без RAW; Android подтверждён. Первоначальный приоритет H1 выше — исторический. Для проверенных режимов/адресов после остановки GMU H1 отвергнута. Остались H2/H3 и отдельный непроверенный actual DMA contract.

E04 записал холодный штатный HFI, включая первый CP_INIT ret0. Десять общих типов allocation совпадают по flags/alignment; size24 и echo host handle подтверждены фактически. Штатный профиль включает функции, отключённые в порте, поэтому различие размеров context records не является основанием править порт. Результаты и ограничения в E04-native-cold-hfi/result.json и allocation-comparison.json.

После E04 пользователь сообщил отказ тача. Обычная перезагрузка восстановила тач, что пользователь подтвердил. Временный образ повторно не запускать до выяснения причины. Сохранённый исходный образ совпал с активным установленным boot_b в проверенном диапазоне. Это исключает простое объяснение устаревшим исходным образом, но не устанавливает причину отказа.
