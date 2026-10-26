from __future__ import annotations

import re

FRONTEND_INCLUDE = [
    re.compile(r"front[\s-]*end", re.I),
    re.compile(r"фронт[\s-]*енд", re.I),
    re.compile(r"react(?:\.?\s*js)?\s*(?:developer|разработ)", re.I),
    re.compile(r"vue(?:\.?\s*js)?\s*(?:developer|разработ)", re.I),
    re.compile(r"angular\s*(?:developer|разработ)", re.I),
    re.compile(r"(?:javascript|typescript)\s*(?:developer|разработ)", re.I),
]

FRONTEND_EXCLUDE = [
    re.compile(r"back[\s-]*end|бэкенд", re.I),
    re.compile(r"full[\s-]*stack|фулстак|fullstack", re.I),
    re.compile(r"\bqa\b|quality assurance|тестиров", re.I),
    re.compile(r"devops|sre|site reliability", re.I),
    re.compile(r"product\s*manager|продуктов(?:ый|ого)\s*менедж", re.I),
    re.compile(r"дизайн|designer|design\b", re.I),
    re.compile(r"\bandroid\b|\bios\b|mobile\s*dev|react[\s-]*native|flutter", re.I),
    re.compile(r"data\s*(?:scientist|analyst)|аналитик\s*данных", re.I),
]

BACKEND_INCLUDE = [
    re.compile(r"back[\s-]*end", re.I),
    re.compile(r"бэкенд", re.I),
    re.compile(r"python\s*(?:developer|разработ|engineer)", re.I),
    re.compile(r"(?:go|golang)\s*(?:developer|разработ|engineer)", re.I),
    re.compile(r"java\s*(?:developer|разработ|engineer)", re.I),
    re.compile(r"node\.?\s*js\s*(?:developer|разработ|engineer)", re.I),
    re.compile(r"php\s*(?:developer|разработ|engineer)", re.I),
    re.compile(r"backend[\s-]*разработ", re.I),
]

BACKEND_EXCLUDE = [
    re.compile(r"front[\s-]*end|фронт[\s-]*енд", re.I),
    re.compile(r"full[\s-]*stack|фулстак|fullstack", re.I),
    re.compile(r"\bqa\b|quality assurance|тестиров", re.I),
    re.compile(r"devops|sre", re.I),
    re.compile(r"дизайн|designer|design\b", re.I),
    re.compile(r"product\s*manager|продуктов(?:ый|ого)\s*менедж", re.I),
]


def _matches(title: str, include: list[re.Pattern], exclude: list[re.Pattern]) -> bool:
    text = " ".join(title.split())
    if not text:
        return False
    for pattern in exclude:
        if pattern.search(text):
            return False
    for pattern in include:
        if pattern.search(text):
            return True
    return False


def is_frontend_vacancy(title: str) -> bool:
    return _matches(title, FRONTEND_INCLUDE, FRONTEND_EXCLUDE)


def is_backend_vacancy(title: str) -> bool:
    if _belongs_to_data_role(title):
        return False
    return _matches(title, BACKEND_INCLUDE, BACKEND_EXCLUDE)


GRAPHIC_INCLUDE = [
    re.compile(r"графическ(?:ий|ого|ая|ое)\s*дизайн", re.I),
    re.compile(r"graphic\s*design(?:er)?", re.I),
    re.compile(r"print\s*design", re.I),
    re.compile(r"полиграф", re.I),
    re.compile(r"visual\s*designer(?!\s*/?\s*product)", re.I),
]

GRAPHIC_EXCLUDE = [
    re.compile(r"product[\s-]*design|продуктов(?:ый|ого)\s*дизайн", re.I),
    re.compile(r"ux/ui|ui/ux|product\s*ux", re.I),
    re.compile(r"communication\s*design|коммуникацион", re.I),
    re.compile(r"front[\s-]*end|back[\s-]*end|бэкенд|фронтенд", re.I),
    re.compile(r"motion|game\s*design|гейм", re.I),
    re.compile(r"интерьер|interior|3d\s*design", re.I),
    re.compile(r"web[\s-]*design|веб[\s-]*дизайн", re.I),
]

COMMUNICATION_INCLUDE = [
    re.compile(r"коммуникацион(?:ный|ного|ная|ное)\s*дизайн", re.I),
    re.compile(r"communication\s*design(?:er)?", re.I),
    re.compile(r"visual\s*communication", re.I),
    re.compile(r"brand\s*communication", re.I),
    re.compile(r"бренд[\s-]*коммуникац", re.I),
]

COMMUNICATION_EXCLUDE = [
    re.compile(r"product[\s-]*design|продуктов(?:ый|ого)\s*дизайн", re.I),
    re.compile(r"ux/ui|ui/ux|product\s*ux", re.I),
    re.compile(r"front[\s-]*end|back[\s-]*end|бэкенд|фронтенд", re.I),
    re.compile(r"графическ(?:ий|ого)\s*дизайн", re.I),
    re.compile(r"graphic\s*design", re.I),
    re.compile(r"motion|game\s*design|гейм", re.I),
]


ART_DIRECTOR_INCLUDE = [
    # На HH пишут и «Арт - директор», и «арт – директор» с длинным тире.
    re.compile(r"арт\s*[-–—]?\s*директор", re.I),
    re.compile(r"art\s*[-–—]?\s*director", re.I),
]

ART_DIRECTOR_EXCLUDE = [
    # «Арт-директор» в РФ — ещё и ведущий программы в баре, клубе или на
    # концертной площадке: это организация мероприятий, а не дизайн.
    re.compile(r"ресторан|кафе|\bбар|гастро|клуб|караоке|кальян|банкет", re.I),
    re.compile(r"концерт|музык|ивент|event|мероприят|отел|гостиниц|лагер", re.I),
    re.compile(r"салон|бьюти|beauty", re.I),
    # Интерьер исключён и в остальных дизайнерских ролях.
    re.compile(r"интерьер|interior", re.I),
]


def is_graphic_designer_vacancy(title: str) -> bool:
    return _matches(title, GRAPHIC_INCLUDE, GRAPHIC_EXCLUDE)


def is_art_director_vacancy(title: str) -> bool:
    return _matches(title, ART_DIRECTOR_INCLUDE, ART_DIRECTOR_EXCLUDE)


def is_communication_designer_vacancy(title: str) -> bool:
    return _matches(title, COMMUNICATION_INCLUDE, COMMUNICATION_EXCLUDE)


DEV_STACK_EXCLUDE = [
    re.compile(r"\bqa\b|quality assurance|тестиров", re.I),
    re.compile(r"devops|sre|site reliability", re.I),
    re.compile(r"дизайн|designer|design\b", re.I),
    re.compile(r"product\s*manager|продуктов(?:ый|ого)\s*менедж", re.I),
    re.compile(r"data\s*(?:scientist|analyst)|аналитик\s*данных", re.I),
    re.compile(r"full[\s-]*stack|фулстак|fullstack", re.I),
]


def is_react_developer_vacancy(title: str) -> bool:
    include = [re.compile(r"react(?:\.?\s*js)?|react[\s-]*разработ", re.I)]
    exclude = DEV_STACK_EXCLUDE + [
        re.compile(r"back[\s-]*end|бэкенд", re.I),
        re.compile(r"\bvue\b", re.I),
        re.compile(r"\bangular\b", re.I),
        re.compile(r"react[\s-]*native", re.I),  # мобильная роль, не веб
    ]
    return _matches(title, include, exclude)


def is_vue_developer_vacancy(title: str) -> bool:
    include = [re.compile(r"vue(?:\.?\s*js)?|vue[\s-]*разработ", re.I)]
    exclude = DEV_STACK_EXCLUDE + [
        re.compile(r"back[\s-]*end|бэкенд", re.I),
        re.compile(r"\breact\b", re.I),
        re.compile(r"\bangular\b", re.I),
    ]
    return _matches(title, include, exclude)


def is_angular_developer_vacancy(title: str) -> bool:
    include = [re.compile(r"angular|angular[\s-]*разработ", re.I)]
    exclude = DEV_STACK_EXCLUDE + [
        re.compile(r"back[\s-]*end|бэкенд", re.I),
        re.compile(r"\breact\b", re.I),
        re.compile(r"\bvue\b", re.I),
    ]
    return _matches(title, include, exclude)


def is_python_developer_vacancy(title: str) -> bool:
    if _belongs_to_data_role(title):
        return False
    include = [re.compile(r"python|python[\s-]*разработ", re.I)]
    exclude = DEV_STACK_EXCLUDE + [
        re.compile(r"front[\s-]*end|фронтенд", re.I),
    ]
    return _matches(title, include, exclude)


def is_java_developer_vacancy(title: str) -> bool:
    if _belongs_to_data_role(title):
        return False
    include = [re.compile(r"java|java[\s-]*разработ", re.I)]
    exclude = DEV_STACK_EXCLUDE + [
        re.compile(r"javascript|typescript", re.I),
        re.compile(r"front[\s-]*end|фронтенд", re.I),
    ]
    return _matches(title, include, exclude)


def is_go_developer_vacancy(title: str) -> bool:
    if _belongs_to_data_role(title):
        return False
    include = [
        re.compile(r"golang|go[\s-]*lang", re.I),
        re.compile(r"\bgo\s+(?:developer|разработ|engineer|backend)", re.I),
        re.compile(r"go[\s-]*разработ", re.I),
    ]
    exclude = DEV_STACK_EXCLUDE + [
        re.compile(r"front[\s-]*end|фронтенд", re.I),
        re.compile(r"google", re.I),
    ]
    return _matches(title, include, exclude)


# PHP: язык и фреймворки — сразу; Битрикс и CMS — только с признаком разработки.
# По «Битрикс24» на HH в основном администраторы, внедренцы и продажи, а
# «Разработчик Битрикс» и «Программист Битрикс 24» пишут на PHP.
_PHP_DEV = r"разработ|программист|developer|engineer|team\s*lead|tech\s*lead|тимлид|техлид"
_PHP_PLATFORM = r"битрикс|bitrix|wordpress|drupal|magento|opencart"
PHP_INCLUDE = [
    re.compile(r"\bphp\b|laravel|symfony|simfony|symphony|\byii\b", re.I),
    re.compile(rf"(?:{_PHP_PLATFORM}).*(?:{_PHP_DEV})|(?:{_PHP_DEV}).*(?:{_PHP_PLATFORM})", re.I),
]
# Fullstack оставляем, в отличие от Python/Java/Go: это четверть PHP-вакансий,
# и бэкенд в них — PHP. Поэтому DEV_STACK_EXCLUDE без fullstack.
PHP_EXCLUDE = [
    re.compile(r"\bqa\b|quality assurance|тестиров", re.I),
    re.compile(r"devops|sre|site reliability", re.I),
    re.compile(r"дизайн|designer|design\b", re.I),
    re.compile(r"product\s*manager|project\s*manager|продуктов(?:ый|ого)\s*менедж", re.I),
    re.compile(r"менеджер\s+(?:по|продукта|проект)|руководител\w*\s+проект|продаж|\bsales\b", re.I),
    re.compile(r"аналитик|analyst", re.I),
    re.compile(r"преподавател|наставник|teacher", re.I),
    # Чистый фронтенд; «Fullstack (PHP + frontend)» не трогаем.
    re.compile(r"^(?!.*(?:full|фулл|фулст|back|бэк)).*(?:front[\s-]*end|фронт[\s-]*енд)", re.I),
    # 1С — не PHP; «1С-Битрикс» — PHP.
    re.compile(r"\b1[сc]\b(?![\s:-]*(?:битрикс|bitrix))", re.I),
]


def is_php_developer_vacancy(title: str) -> bool:
    if _belongs_to_data_role(title):
        return False
    return _matches(title, PHP_INCLUDE, PHP_EXCLUDE)


# C# / .NET. «.NET» — только отдельным словом: не «example.net» и не «ASP.NET»
# внутри другого слова (ASP.NET ловится отдельно). Unity и геймдев — это C#, но
# другой рынок: подписчику бэкенда такие вакансии не нужны.
CSHARP_INCLUDE = [
    re.compile(r"(?<!\w)c\s*#|c[\s-]*sharp|csharp", re.I),
    re.compile(r"(?<!\w)\.net\b|dotnet|asp\.?\s*net|blazor", re.I),
]
CSHARP_EXCLUDE = DEV_STACK_EXCLUDE + [
    re.compile(r"front[\s-]*end|фронт[\s-]*енд", re.I),
    re.compile(r"\bunity\b|game|гейм|\bигр", re.I),
]


def is_csharp_developer_vacancy(title: str) -> bool:
    if _belongs_to_data_role(title):
        return False
    return _matches(title, CSHARP_INCLUDE, CSHARP_EXCLUDE)


# --- IT Project Manager (26.10.2026) ---
# Роль «Project Manager» уже была и снята: на HH под этим названием стройка,
# ивенты и продажи. Теперь HH опрашивается только IT-формулировками (см. роль),
# а Хабр, GetMatch и GeekJob — площадки только про IT. Фильтр отсекает то,
# что проскакивает и там: проектные продажи, аналитиков, юристов, экономистов,
# разработчиков с пометкой «проектная работа».
IT_PM_INCLUDE = [
    re.compile(r"project\s*manager|проджект[\s-]*менеджер", re.I),
    # До двух слов между: «Менеджер IT/Saas проектов», «Руководитель кросс-блочного проекта».
    re.compile(r"(?:менеджер|руководител\w*)\s+(?:[\w/]+[\s-]+){0,2}проект(?:а|ов)\b", re.I),
    re.compile(r"менеджер\s+по\s+проектам", re.I),
    re.compile(r"delivery\s*manager|program\s*manager|technical\s+project\s+lead", re.I),
]
IT_PM_EXCLUDE = [
    re.compile(r"product\s*(?:manager|owner)|продукт\w*\s+менедж|менеджер\s+продукт", re.I),
    re.compile(r"\bаналитик\b|analyst", re.I),  # «аналитика» в описании направления — не аналитик
    re.compile(r"продаж|sales|по\s+развитию|account", re.I),
    re.compile(r"юрист|юрисконсульт|экономист|бухгалт|обучени", re.I),
    re.compile(r"строител|строй|монтаж|проектировщ|ремонт|недвижим|девелопмент|ивент|event|мероприят", re.I),
    re.compile(r"healthcare|cost\s+segregation|кредитн\w*\s+риск", re.I),
    re.compile(r"дизайн|designer|разработчик|developer|программист|engineer\b|инженер", re.I),
]


def is_it_project_manager_vacancy(title: str) -> bool:
    return _matches(title, IT_PM_INCLUDE, IT_PM_EXCLUDE)


# --- DevOps / SRE (25.10.2026) ---
# Платформенные инженеры — только без языка в названии: «Go Platform Engineer»
# пишет на Go и уходит в Backend. Чистый MLOps — роль ML-инженера, сисадмины —
# отдельная профессия; «Системный администратор с функцией DevOps» ловится по слову DevOps.
DEVOPS_INCLUDE = [
    re.compile(r"dev\s*-?\s*(?:sec)?\s*ops", re.I),
    re.compile(r"\bsre\b|site\s*reliability|надёжност\w*\s+и\s+эксплуатац|надежност\w*\s+и\s+эксплуатац", re.I),
    re.compile(r"\bplatform\s+engineer", re.I),
]
DEVOPS_EXCLUDE = [
    re.compile(r"\bqa\b|\baqa\b|тестиров|тестировщ", re.I),
    re.compile(r"аналитик|analyst", re.I),
    re.compile(r"дизайн|designer", re.I),
    re.compile(r"product\s*(?:manager|owner)|менеджер|manager|presale|пресейл|продаж|sales|маркетолог|marketing|рекрутер|recruit", re.I),
    re.compile(r"консультант|consultor|consultant", re.I),
    re.compile(r"data\s+platform", re.I),  # инженер данных, роль Data Engineer
    # Платформенный инженер с языком в названии — разработчик.
    re.compile(r"\b(?:go|golang|java|python|php|c\+\+|c#|kotlin|rust|node\.?js)\b.*platform\s+engineer|platform\s+engineer.*\b(?:go|golang|java|python|php)\b", re.I),
]


def is_devops_vacancy(title: str) -> bool:
    return _matches(title, DEVOPS_INCLUDE, DEVOPS_EXCLUDE)


# --- Fullstack и мобильная разработка (24.10.2026) ---
# Общее: не забирать тестировщиков, аналитиков, дизайнеров и менеджеров. На HH
# «Fullstack-аналитик», «Fullstack QA», «Дизайнер Fullstack» — около трети
# заголовков со словом fullstack.
NOT_DEVELOPER_EXCLUDE = [
    re.compile(r"\bqa\b|\baqa\b|quality assurance|тестиров|тестировщ", re.I),
    re.compile(r"аналитик|analyst", re.I),
    re.compile(r"дизайн|designer|design\b", re.I),
    re.compile(r"product\s*(?:manager|owner)|продуктов\w*\s*менедж|менеджер\s+продукта", re.I),
    re.compile(r"маркетолог|marketing|\bsmm\b|рекрутер|recruit", re.I),
]
_DEV_CONTEXT = r"разработ|программист|developer|engineer|\bdev\b|team\s*lead|tech\s*lead|тимлид|техлид"


def is_fullstack_vacancy(title: str) -> bool:
    include = [re.compile(r"full[\s-]*stack|фул+[\s-]*ст[еэ]к|фулстак|разработчик\w*\s+полного\s+цикла", re.I)]
    return _matches(title, include, NOT_DEVELOPER_EXCLUDE)


# Мобильная разработка. На HH мало: за 3 дня iOS ~4, Android ~5, Flutter ~2,
# React Native ~2 — плюс Хабр, GetMatch и мир. Стек в названии обязателен:
# «Мобильный разработчик» без стека никому из ролей не уходит.
_MOBILE_NOISE = re.compile(r"ремонт|сервисн|склад|кладовщ|сборщик|продаж|sales", re.I)
MOBILE_EXCLUDE = NOT_DEVELOPER_EXCLUDE + [_MOBILE_NOISE]


def is_flutter_developer_vacancy(title: str) -> bool:
    include = [re.compile(r"flutter|\bdart\b", re.I)]
    return _matches(title, include, MOBILE_EXCLUDE)


def is_ios_developer_vacancy(title: str) -> bool:
    include = [
        re.compile(r"\bios\b|swiftui|objective[\s-]*c\b", re.I),
        # Swift — только рядом с разработкой: «сопровождение SWIFT» — банковские платежи.
        re.compile(rf"\bswift\b.*(?:{_DEV_CONTEXT})|(?:{_DEV_CONTEXT}).*\bswift\b", re.I),
    ]
    return _matches(title, include, MOBILE_EXCLUDE)


def is_android_developer_vacancy(title: str) -> bool:
    include = [
        re.compile(r"\bandroid\b|андроид", re.I),
        # Kotlin без признаков мобильной разработки — чаще бэкенд («Java/Kotlin разработчик»).
        re.compile(r"\bkotlin\b.*(?:mobile|мобильн|jetpack|compose)|(?:mobile|мобильн).*\bkotlin\b", re.I),
    ]
    return _matches(title, include, MOBILE_EXCLUDE)


def is_react_native_developer_vacancy(title: str) -> bool:
    include = [re.compile(r"react[\s-]*native", re.I)]
    return _matches(title, include, MOBILE_EXCLUDE)


# --- Продукт и QA ---
# Общий фон для менеджерских и QA-ролей: не забирать дизайн и разработку.
PRODUCT_QA_EXCLUDE = [
    re.compile(r"дизайн|designer|design\b", re.I),
    re.compile(r"front[\s-]*end|back[\s-]*end|фронтенд|бэкенд", re.I),
    re.compile(r"(?:python|java|golang|react|vue|angular|php)\s*(?:developer|разработ|engineer)", re.I),
    re.compile(r"devops|sre|site reliability", re.I),
    re.compile(r"аналитик|analyst", re.I),
]

# Отрасли, где то же название должности значит совсем другую работу: HH отдаёт
# «Product Manager (медицинские изделия)» и «Продакт-менеджер товарного
# направления» по тем же запросам и той же профобласти, что и продакта в IT.
NON_IT_DOMAIN_EXCLUDE = [
    re.compile(r"строительств|монтаж|прораб|металлоконструкц", re.I),
    re.compile(r"медицин|стоматолог|фармац|клиник", re.I),
    re.compile(r"категорийн|товарн|ритейл|розниц|закуп|продаж", re.I),
    re.compile(r"недвижим|интерьер|мебел|трикотаж|одежд|бренд", re.I),
    re.compile(r"продюсер|vfx", re.I),
]

# Автоматизация тестирования — отдельная роль, поэтому её термины нужны и как
# include для qa_automation, и как exclude для qa_manual.
QA_AUTOMATION_TERMS = [
    re.compile(r"\baqa\b|\bsdet\b", re.I),
    re.compile(r"автотестировщик|автотест", re.I),
    re.compile(r"автоматизатор", re.I),
    re.compile(r"тестировщик[\s-]*автоматизатор", re.I),
    re.compile(r"автоматизац\w*\s+тестир|автоматизиров\w*\s+тестир", re.I),
    re.compile(r"(?:test|qa)\s*automation|automation\s*(?:qa|test)", re.I),
    # «Automation» само по себе — только рядом с QA/тестами или как Automation
    # Engineer: на Хабре, GetMatch и западных площадках нет профобласти HH, и
    # туда попадали «Marketing Automation», «Messaging Automation» у продаж.
    re.compile(r"\b(?:qa|test\w*|sdet)\b.*\bautomation\b|\bautomation\b.*\b(?:qa|test\w*)\b", re.I),
    # «Automation Engineer» в начале названия; «Workflow/AI Automation Engineer» — не QA.
    re.compile(r"^(?:(?:senior|middle|junior|lead|sr\.?)\s+)?automation\s+(?:engineer|developer)\b", re.I),
]


# «Менеджер по продукту» по-русски — ещё и ведение товарной линейки в фарме,
# FMCG, одежде, дистрибуции техники. В ночной выдаче HH таких было около
# четверти. Отраслевое слово не отсекает вакансию, если рядом есть цифровой
# признак: «Product manager, fashion — развитие сайта и приложения» — это
# цифровой продукт, а «Product Manager (Fashion)» в бренде одежды — ассортимент.
_PM_DIGITAL = (
    r"digital|сайт|приложени|\bapp\b|e-?com|онлайн|online|мобильн|mobile|платформ|platform"
    r"|saas|\bit\b|\bит\b|\bai\b|\bии\b|веб|web|цифров|интернет"
)
_PM_GOODS_DOMAINS = (
    r"препарат|\bбад|\botc\b|\brx\b|фарм|неврол|психиатр|immunolog|иммунол|офтальм|эндоскоп"
    r"|госпитал|аптек|косметик|cosmetic|парфюм|аромат|beauty|fmcg|пищев|деликатес|лакомств"
    r"|кофейн|упаковк|r&d|\bдич|обув|джинс|fashion|швейн|\bмерч|ювелир|аксессуар|фабрик|байер"
    r"|китай|продукци|физическ\w*\s+товар|девелопмент|садов"
    r"|\bибп\b|\bssd\b|картридж|телевизор|бытов\w*\s+техник|климатич|сварочн"
    r"|строительн\w*\s+(?:хими|инструмент)|крепёж|крепеж|\bбан[иья]\b|сейф|свч|видеонаблюд"
    r"|\bреле\b|датчик|серверн\w*\s+шкаф|netapp|grandstream|мультимеди|компьютерн\w*\s+техник"
    r"|этикетк|энерги|road\s+construction|оборудование\s+для"
)
PRODUCT_MANAGER_GOODS_EXCLUDE = [
    re.compile(rf"^(?!.*(?:{_PM_DIGITAL})).*(?:{_PM_GOODS_DOMAINS})", re.I),
]


def is_product_manager_vacancy(title: str) -> bool:
    include = [
        re.compile(r"product\s*manager", re.I),
        re.compile(r"продакт[\s-]*менедж", re.I),
        re.compile(r"продукт[\s-]*менедж", re.I),
        re.compile(r"продуктов(?:ый|ого)\s*менедж", re.I),
        re.compile(r"менеджер\s*продукт", re.I),
        re.compile(r"менеджер\s+по\s+продукт", re.I),
    ]
    exclude = PRODUCT_QA_EXCLUDE + NON_IT_DOMAIN_EXCLUDE + PRODUCT_MANAGER_GOODS_EXCLUDE + [
        re.compile(r"project|проджект", re.I),
        re.compile(r"owner|оунер|владелец", re.I),
        re.compile(r"\bqa\b|тестиров", re.I),
    ]
    return _matches(title, include, exclude)


def is_product_owner_vacancy(title: str) -> bool:
    include = [
        re.compile(r"product\s*owner", re.I),
        re.compile(r"продакт[\s-]*оунер", re.I),
        re.compile(r"владелец\s*продукта", re.I),
    ]
    exclude = PRODUCT_QA_EXCLUDE + NON_IT_DOMAIN_EXCLUDE + [
        re.compile(r"project|проджект", re.I),
        re.compile(r"\bqa\b|тестиров", re.I),
    ]
    return _matches(title, include, exclude)




def is_qa_manual_vacancy(title: str) -> bool:
    include = [
        re.compile(r"\bqa\b", re.I),
        re.compile(r"quality\s*assurance", re.I),
        re.compile(r"тестировщик", re.I),
        re.compile(r"тестирован", re.I),
    ]
    exclude = PRODUCT_QA_EXCLUDE + QA_AUTOMATION_TERMS + [
        re.compile(r"manager|менедж|owner", re.I),
    ]
    return _matches(title, include, exclude)


def is_qa_automation_vacancy(title: str) -> bool:
    exclude = PRODUCT_QA_EXCLUDE + [
        re.compile(r"manager|менедж|owner", re.I),
    ]
    return _matches(title, QA_AUTOMATION_TERMS, exclude)


# --- Data ---
# Профобласти HH здесь не помогают: ML-инженеров работодатели раскладывают по
# пяти разным областям. Названия у data-профессий зато однозначные, так что
# роль решается по заголовку.

DATA_SCIENTIST_INCLUDE = [
    re.compile(r"data[\s-]*scien", re.I),
    re.compile(r"дата[\s-]*сайент", re.I),
]

# ML-роль определяется самой должностью. «LLM» в скобках у разработчика —
# «Senior .NET Developer (LLM / RAG)», «Java Backend-разработчик AI / LLM
# Platform» — это разработчик, а не ML-инженер, и остаётся в своей роли.
ML_ENGINEER_INCLUDE = [
    # ML как должность, а не как домен: «Golang-разработчик (домен AI&ML)» —
    # Go-разработчик, тот же принцип, что с LLM ниже.
    re.compile(
        r"\bml[\s/-]*(?:engineer|инженер|разработ|developer|researcher|research"
        r"|специалист|lead|лид|tech\s*lead|team\s*lead|architect|архитектор)",
        re.I,
    ),
    re.compile(r"(?:head\s+of|команд\w*|руководител\w*|направлени\w*)\s+ml\b", re.I),
    re.compile(r"machine\s*learning|машинн\w*\s+обучени", re.I),
    re.compile(r"mlops|llmops|mlsecops", re.I),
    re.compile(r"\bllm[\s-]*(?:engineer|инженер|разработ|developer)", re.I),
    re.compile(r"\bai\b[\w\s/&-]{0,20}?\b(?:engineer|инженер|researcher)", re.I),
    re.compile(r"computer\s*vision|компьютерн\w*\s+зрени", re.I),
    re.compile(r"deep\s*learning", re.I),
    re.compile(r"\bai\b[\s/-]*(?:tech\s*)?lead|tech\s*lead\s+ai\b", re.I),
    re.compile(r"agentic\s+engineer|prompt\s*engineer|промпт[\s-]*инженер", re.I),
]

ML_ENGINEER_EXCLUDE = [
    re.compile(r"data[\s-]*scien|дата[\s-]*сайент", re.I),  # это Data Scientist
    re.compile(r"\bаналитик|\banalyst", re.I),
    re.compile(r"\bqa\b|тестиров", re.I),
    re.compile(r"owner|manager|менеджер", re.I),
    re.compile(r"разметк|разметчик", re.I),
]

DATA_ENGINEER_INCLUDE = [
    # Data Quality / Platform / Integration Engineer — одно слово между.
    re.compile(r"data[\s-]+(?:\w+[\s-]+)?engineer|analytics\s*engineer", re.I),
    re.compile(r"(?:data|дата)[\s-]*инженер|инженер\w*\s+данных", re.I),
    re.compile(r"\bdwh\b|\betl\b|\belt\b", re.I),
    re.compile(r"хранилищ\w*\s+данных|big\s*data", re.I),
]

DATA_ENGINEER_EXCLUDE = [
    # «Аналитик DWH», «Системный аналитик (хранилище данных)» — аналитики,
    # а «Аналитик-разработчик DWH» — разработчик.
    re.compile(r"\bаналитик(?![\s-]*разработ)|\banalyst", re.I),
    re.compile(r"дата[\s-]*центр|data\s*cent|\bцод", re.I),
    re.compile(r"data[\s-]*scien", re.I),
    re.compile(r"\bqa\b|тестиров", re.I),
    re.compile(r"owner", re.I),
]

DATA_ANALYST_INCLUDE = [
    re.compile(r"data[\s-]*(?:analy|аналит)|дата[\s-]*аналит", re.I),
    # «Аналитик данных», а также с одним словом между: «Аналитик баз данных»,
    # «Аналитик клиентских данных», «Ведущий аналитик больших данных».
    re.compile(r"аналитик\w*\s+(?:\w+\s+)?данных", re.I),
    re.compile(r"аналитик\w*\s+(?:dwh|sql)\b|\bsql[\s-]*аналитик", re.I),
    re.compile(r"анализ\w*\s+данных", re.I),
    # BI — только как должность: «BI на платформе» бывает и у разработчиков.
    re.compile(r"\bbi[\s-]*(?:аналит|разработ|инженер|специалист|analyst|developer|engineer)", re.I),
    re.compile(r"(?:аналитик|разработчик|специалист)\w*\s+(?:power\s*)?bi\b", re.I),
]

DATA_ANALYST_EXCLUDE = [
    re.compile(r"продуктов\w*\s+аналит|product\s*analy", re.I),  # продуктовый аналитик
    re.compile(r"data[\s-]*scien", re.I),
    re.compile(r"системн\w*\s+аналит|system\s*analy", re.I),
    re.compile(r"\bqa\b|тестиров", re.I),
]

PRODUCT_ANALYST_INCLUDE = [
    re.compile(r"продуктов\w*\s+аналит", re.I),
    re.compile(r"product\s*analy", re.I),
    re.compile(r"аналитик\s+продукта\b", re.I),
]

PRODUCT_ANALYST_EXCLUDE = [
    # Аналитика для продавцов на маркетплейсах — другая работа, не продукт в IT.
    re.compile(r"маркетплейс|wildberries|поиск\s+ниш", re.I),
    # «Продуктолог», «тренд-аналитик» — товарная экспертиза в ритейле.
    re.compile(r"продуктолог|тренд[\s-]*аналит", re.I),
    re.compile(r"owner|manager|менеджер", re.I),
]


def is_data_scientist_vacancy(title: str) -> bool:
    return _matches(title, DATA_SCIENTIST_INCLUDE, [])


def is_ml_engineer_vacancy(title: str) -> bool:
    return _matches(title, ML_ENGINEER_INCLUDE, ML_ENGINEER_EXCLUDE)


def is_data_engineer_vacancy(title: str) -> bool:
    return _matches(title, DATA_ENGINEER_INCLUDE, DATA_ENGINEER_EXCLUDE)


def is_data_analyst_vacancy(title: str) -> bool:
    return _matches(title, DATA_ANALYST_INCLUDE, DATA_ANALYST_EXCLUDE)


def is_product_analyst_vacancy(title: str) -> bool:
    return _matches(title, PRODUCT_ANALYST_INCLUDE, PRODUCT_ANALYST_EXCLUDE)


def _belongs_to_data_role(title: str) -> bool:
    """Data/ML-инженеры с языком в названии раньше уходили в Backend.

    Бэкенд отдаёт ровно то, что забирают data-роли, — не больше, чтобы
    вакансия не потерялась между ролями.
    """
    return is_ml_engineer_vacancy(title) or is_data_engineer_vacancy(title)


DATA_GOVERNANCE_INCLUDE = [
    re.compile(r"data[\s-]*governance|datagov", re.I),
    re.compile(r"data[\s-]*steward|data[\s-]*quality|качеств\w*\s+(?:\w+\s+)?данных", re.I),
    re.compile(r"управлени\w*\s+(?:мастер[\s-]*)?данными|data[\s-]*management", re.I),
    re.compile(r"\bmdm\b|master[\s-]*data|мастер[\s-]*данн|дата[\s-]*каталог|data[\s-]*catalog", re.I),
    re.compile(r"методолог\w*\s+(?:управления\s+)?данн", re.I),
    # НСИ — нормативно-справочная информация, по сути те же мастер-данные.
    re.compile(r"\bнси\b", re.I),
]

DATA_GOVERNANCE_EXCLUDE = [
    # Учётная работа в 1С и Excel, госслужба по разрядам — не governance.
    # 1С вместе с MDM — уже мастер-данные, это не отсекаем.
    re.compile(r"^(?!.*\bmdm\b).*\b1[сc]\b", re.I),
    re.compile(
        r"excel|разряд|супервайзер|делопроизвод|ввод\w*\s+данн"
        r"|ведени\w*\s+(?:нормативн|справочник|нси)|^оператор|оператор\w*\s+(?:пк|ввода|баз|нси)"
        r"|склад|техническ\w*\s+документац",
        re.I,
    ),
    re.compile(r"devops|поддержк|сопровожден|support", re.I),
    re.compile(r"образоват|обучени|registrar|расч[её]т", re.I),
    # MDM у безопасников и админов — Mobile Device Management, не мастер-данные.
    re.compile(r"\bиб\b|\bdlp\b|антивирус|mobile\s+device|intune|системн\w*\s+администратор", re.I),
    re.compile(r"работе\s+с\s+клиент|продаж|\bsales\b|account", re.I),
    # Разработчик в подразделении «Центр DataGov» — бэкенд, а не governance.
    re.compile(r"серверн\w*\s+част|backend|бэкенд", re.I),
]


# --- Руководители ---
# Уровень директоров и руководителей направлений. Тимлидов сюда не берём — их
# ловят профильные роли, а руководитель, подписанный на эту категорию, не
# должен получать вакансии своей команды. «Начальник» — то же, что руководитель.
LEAD_RU = r"(?:руководител|начальник)\w*"

LEADER_EXCLUDE = [
    # Уровень команды в любой форме: «Руководитель группы», «…подгруппы»,
    # «…ML-группы», «Начальник AI-команды», «тим-лид». «Группа компаний» —
    # это холдинг, а не команда.
    re.compile(LEAD_RU + r"\s+(?:[\w-]+[\s-]+)?(?:под)?групп(?!\w*\s+компани)", re.I),
    re.compile(LEAD_RU + r"\s+(?:[\w-]+[\s-]+)?команд", re.I),
    re.compile(r"team[\s-]*lead|тим[\s-]*лид", re.I),
    # Ассистент руководителя — да, «AI-ассистенты» как продукт — нет.
    re.compile(
        r"(?:ассистент|помощник|секретар)\w*\s+(?:руководител|директор|генеральн|основател"
        r"|ceo|коммерческ|технич)|бизнес[\s-]*ассистент|(?:personal|executive)\s+assistant"
        r"|^(?:ассистент|помощник|секретар)",
        re.I,
    ),
    re.compile(r"продаж|\bsales\b|pre-?sale|аккаунт|account", re.I),
]

HEAD_OF_DATA_INCLUDE = [
    re.compile(r"chief\s+data|\bcdo\b", re.I),
    re.compile(r"(?:head|director|vp)\s+of\s+(?:data|analytics|bi)\b", re.I),
    re.compile(r"директор\w*\s+по\s+(?:управлению\s+)?(?:данн|аналитик)", re.I),
    re.compile(r"директор\w*\s+по\s+(?:\w+\s+){1,3}данн", re.I),
    re.compile(LEAD_RU + r"\s+(?:\w+\s+){0,3}(?:аналитик\w*|анализ\w*)\s+данных", re.I),
    re.compile(LEAD_RU + r"\s+(?:\w+\s+){0,3}по\s+данным", re.I),
    # Руководитель продуктовой аналитики — тоже руководитель в Data.
    re.compile(
        r"(?:руководител|начальник|директор|head)\w*\s+(?:of\s+)?(?:\w+\s+){0,2}"
        r"(?:продуктов\w*\s+аналитик|product\s+analytics)",
        re.I,
    ),
    re.compile(LEAD_RU + r"\s+\w+\s+\(bi\b", re.I),
    re.compile(
        r"(?:руководител|начальник|директор)\w*\s+(?:отдела|направления|департамента|дирекции"
        r"|управления|службы|центра)\s+(?:bi\b|данных\b)",
        re.I,
    ),
    # Голое «аналитики» — только с признаком данных рядом: без него это аналитика
    # животноводства, доходности, аудита.
    re.compile(
        r"^(?=.*(?:руководител|начальник|директор)\w*\s+(?:отдела|направления|департамента"
        r"|дирекции|управления|службы|центра)\s+аналитики\b)"
        r"(?=.*(?:python|sql|\bdata\b|\bbi\b|dwh|\bml\b|\bai\b|данн|метрик|a/b|продукт))",
        re.I,
    ),
]

HEAD_OF_DATA_EXCLUDE = [
    # «CDO» бывает и Chief Digital, Design или Development Officer.
    re.compile(r"digital|цифров|трансформац", re.I),
    re.compile(r"chief\s+(?:design|development)|(?:design|development)\s+officer", re.I),
    re.compile(LEAD_RU + r"\s+проект|project\s+manager", re.I),
    # «Аналитика» по-русски — ещё и финансы, продажи, логистика, цены.
    re.compile(
        r"финанс|инвест|логист|снабж|закуп|\bhr\b|персонал|кадр|ценообраз|\bцен\b|цены|ценов"
        r"|смет|строит|недвиж|рынк|маркетинг|marketing|crm|лидоген|веб[\s-]*аналит"
        r"|бизнес[\s-]*анали|системн|безопасн|\bиб\b|угроз|взыскан|мошенни|стратеги|рейтинг"
        r"|одежд|fashion|химик|консалт",
        re.I,
    ),
]

HEAD_OF_AI_INCLUDE = [
    re.compile(r"chief\s+ai|\bcaio\b", re.I),
    re.compile(r"(?:head|director|vp)\s+of\s+(?:\w+\s+)?(?:ai|genai|ml|mlops|machine\s+learning)\b", re.I),
    re.compile(r"директор\w*\s+по\s+(?:искусственн\w+\s+интеллект|ии\b|ai\b)", re.I),
    # \b после аббревиатур: «Руководитель MLM-направления» — сетевой маркетинг.
    re.compile(
        LEAD_RU + r"\s+(?:\w+[\s-]+){0,3}(?:(?:ai|ии|ml|mlops)\b|искусственн\w*\s+интеллект"
        r"|\"искусственн\w*\s+интеллект|машинн\w*\s+обучени)",
        re.I,
    ),
]

HEAD_OF_AI_EXCLUDE = [
    # Продажи, маркетинг, контент и проекты в AI-компаниях — не руководство AI.
    re.compile(r"маркетинг|marketing|маркетолог|\bseo\b|контент|content|креатор", re.I),
    re.compile(LEAD_RU + r"\s+проект|project\s+manager|(?:ai|ии)[\s-]+проект", re.I),
    re.compile(r"образова|профессор|аспирант|академи|тренер|trainer", re.I),
    re.compile(r"информационн\w*\s+безопасн|\bиб\b|арт[\s-]*директор|магазин|шоурум", re.I),
]

HEAD_OF_DESIGN_INCLUDE = [
    re.compile(r"(?:head|director|vp)\s+of\s+(?:\w+\s+)?(?:design|ux|ui)\b", re.I),
    re.compile(r"design\s+director|chief\s+design\s+officer|дизайн[\s-]*директор", re.I),
    re.compile(r"директор\w*\s+(?:по\s+)?(?:\w+\s+)?дизайн", re.I),
    re.compile(LEAD_RU + r"\s+(?:\w+[\s/-]+){0,2}дизайн", re.I),
]

HEAD_OF_DESIGN_EXCLUDE = [
    re.compile(r"организацион\w*\s+дизайн|оргдизайн", re.I),  # это HR
    re.compile(r"интерьер|interior|ландшафт|благоустр|архитектур|design\s*&\s*build|строител", re.I),
    re.compile(r"одежд|fashion|вышивк|экипировк|печат|\bdtf\b|мебел|ювелир|обув|игруш", re.I),
    re.compile(r"sound|instructional|союз", re.I),
    re.compile(
        LEAD_RU + r"\s+проект|дизайн[\s-]*проект|кафедр|школ\w*\s+дизайн|университет|преподав",
        re.I,
    ),
    # Арт-директор — своя роль; в руководителей дизайна — только если прямо
    # написано «Head of Design» или «руководитель дизайна».
    re.compile(
        r"^(?!.*(?:head\s+of\s+design|руководител\w*\s+(?:\w+\s+)?дизайн)).*арт[\s-]*директор",
        re.I,
    ),
]

HEAD_OF_PRODUCT_INCLUDE = [
    re.compile(r"\bcpo\b|chief\s+product\s+officer", re.I),
    re.compile(r"(?:head|director|vp)\s+of\s+(?:\w+\s+){0,2}products?\b", re.I),
    re.compile(r"product\s+director|директор\w*\s+(?:по\s+)?(?:\w+\s+)?продукт", re.I),
    re.compile(
        LEAD_RU + r"\s+(?:продуктового\s+(?:направления|департамента)"
        r"|департамента\s+продукт|(?:it|ит)[\s-]+продукт)",
        re.I,
    ),
]

HEAD_OF_PRODUCT_EXCLUDE = [
    re.compile(r"маркетинг|marketing|\bpmm\b|placement", re.I),
    re.compile(r"дизайн|design|аналит|analytic", re.I),  # руководители дизайна и Data
    re.compile(r"одежд|fashion|продуктолог|ассортимент", re.I),
    re.compile(
        r"питани|общепит|пицц|ресторан|магазин|супермаркет|продуктов\w*\s+сет|недвиж|биотех"
        r"|фарм|медицин|закуп|туропер|туристич|сопровожден",
        re.I,
    ),
    # CPO — ещё и Chief People Officer и Chief Production Officer.
    # «CPO (HR Tech)» — продукт в HR-tech, его не трогаем.
    re.compile(r"chief\s+people|people\s+officer|по\s+персоналу|по\s+кадр", re.I),
    re.compile(r"производств|двер|смазоч", re.I),
    # Продуктовые линейки оборудования — промышленность, а не цифровой продукт.
    re.compile(r"тепл|насос|прибор|кипиа|электрообогрев|электротех|оборудован|hardware", re.I),
    re.compile(r"art\s*director|арт[\s-]*директор|технич\w*\s+директор", re.I),
]

HEAD_OF_ENGINEERING_INCLUDE = [
    re.compile(r"\bcto\b|\bcpto\b|chief\s+technology\s+officer", re.I),
    re.compile(
        r"engineering\s+manager|vp\s+(?:of\s+)?engineering"
        r"|director\s+of\s+(?:engineering|software|development)",
        re.I,
    ),
    # «Development» без уточнения — разработка, но не People / Business /
    # Corporate / Infrastructure Development.
    re.compile(
        r"head\s+of\s+(?:\w+\s+)?(?:engineering|software|frontend|backend|mobile|platform)\b"
        r"|head\s+of\s+(?:(?:software|frontend|backend|mobile|web|game|platform|it)\s+)?development\b",
        re.I,
    ),
    re.compile(r"директор\w*\s+по\s+(?:\w+\s+)?разработк", re.I),
    re.compile(
        LEAD_RU + r"\s+(?:(?:отдела|департамента|направления|управления|дирекции|центра)\s+)?"
        r"(?:\w+\s+)?разработк",
        re.I,
    ),
    # «Технический директор» — только с IT-признаком в любом месте названия: без
    # него это обычно стройка или завод, и профобласть 125 у HH их не отделяет.
    re.compile(
        r"^(?=.*технич\w*\s+директор)(?=.*(?:\bit\b|\bит\b|разработ|software|digital"
        r"|saas|геймдев|gamedev|финтех|fintech|онлайн|интернет|платформ|\bai\b|\bии\b))",
        re.I,
    ),
]

HEAD_OF_ENGINEERING_EXCLUDE = [
    # «Директор по разработке» в выдаче HH — это и девелопмент, и Business Development.
    re.compile(
        r"девелоп|business\s*development|corporate\s+development|развити\w*\s+бизнеса", re.I
    ),
    # Кириллическое «СТО» (станция техобслуживания) здесь не исключаем: оно же
    # бывает CTO, набранным кириллицей, — «СТО/Chief Technology Officer».
    re.compile(
        r"строит|производств|завод|монтаж|жкх|автосервис|продукци|издели|прибор|оборудован"
        r"|конструкт|электротех|станци|\bгип\b|главн\w*\s+инженер|ателье|швейн|одежд"
        r"|ресторан|отел|гостиниц|недвиж|месторожд",
        re.I,
    ),
    # Эксплуатация — стройка и ЖКХ, но не «разработка и эксплуатация ПО».
    re.compile(r"^(?!.*(?:(?-i:\bПО\b)|software|программн)).*эксплуатац", re.I),
    # Системы менеджмента качества, склады и логистика, продвижение — не разработка ПО.
    re.compile(r"\bсмк\b|менеджмент\w*\s+качеств|сортировоч|склад|логист|продвижен|светотехн", re.I),
    # Разработка не ПО: фармацевтика, химия, агро, напитки, учебные программы.
    re.compile(
        r"фармацевт|лекарств|клеев|хими|культивир|напит|образовательн|усилител|\bрэа\b"
        r"|радиоэлектрон|\bнпз\b|планов\s+развити|медиа[\s-]*проект",
        re.I,
    ),
    # «Директор по разработке розничных продуктов» в банке — это продукт; но
    # «разработка программных продуктов» — это разработка.
    re.compile(
        r"^(?!.*программн).*(?:разработк\w*\s+(?:\w+\s+){0,3}продукт|product\s+development)",
        re.I,
    ),
    re.compile(LEAD_RU + r"\s+проект|project\s+manager", re.I),
]

def is_data_governance_vacancy(title: str) -> bool:
    return _matches(title, DATA_GOVERNANCE_INCLUDE, DATA_GOVERNANCE_EXCLUDE)


def is_head_of_data_vacancy(title: str) -> bool:
    return _matches(title, HEAD_OF_DATA_INCLUDE, LEADER_EXCLUDE + HEAD_OF_DATA_EXCLUDE)


def is_head_of_ai_vacancy(title: str) -> bool:
    return _matches(title, HEAD_OF_AI_INCLUDE, LEADER_EXCLUDE + HEAD_OF_AI_EXCLUDE)


def is_head_of_design_vacancy(title: str) -> bool:
    return _matches(title, HEAD_OF_DESIGN_INCLUDE, LEADER_EXCLUDE + HEAD_OF_DESIGN_EXCLUDE)


def is_head_of_product_vacancy(title: str) -> bool:
    return _matches(title, HEAD_OF_PRODUCT_INCLUDE, LEADER_EXCLUDE + HEAD_OF_PRODUCT_EXCLUDE)


def is_head_of_engineering_vacancy(title: str) -> bool:
    return _matches(
        title, HEAD_OF_ENGINEERING_INCLUDE, LEADER_EXCLUDE + HEAD_OF_ENGINEERING_EXCLUDE
    )
