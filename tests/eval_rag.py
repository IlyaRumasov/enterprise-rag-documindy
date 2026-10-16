"""Регресійна перевірка якості RAG для DocuMindy.

Задає запитання chatflow Flowise і перевіряє:
  - у топі знайдених джерел є очікуваний документ (за фрагментом назви файлу);
  - для питань без відповіді в базі бот чесно каже, що не знайшов.

Змінні середовища (значення не зберігаються в репозиторії):
  FLOWISE_URL          напр. https://flowise.example.com
  FLOWISE_CHATFLOW_ID  ID chatflow "DocuMindy RAG"
  FLOWISE_API_KEY      ключ API Flowise

Запуск:  python tests/eval_rag.py
Код завершення 0, якщо всі перевірки пройдені, інакше 1.
"""
import json
import os
import sys
import urllib.request
import uuid

# (запитання, фрагмент назви очікуваного файлу (або кортеж допустимих), None якщо відповіді в базі немає)
CASES = [
    ("Скільки символів має бути в паролі користувача?", "PASSWORD POLICY"),
    ("Какие требования к паролям сервисных аккаунтов?", "PASSWORD POLICY"),
    ("Як часто потрібно змінювати пароль?", "PASSWORD POLICY"),
    ("Що таке власник ІТ активу і що він робить?", ("ACCESS CONTROL", "ACCESS MANAGEMENT")),
    ("Когда предоставляется административный доступ новым сотрудникам?", "АДМИНИСТРАТИВНОГО"),
    ("Що робити з гостьовою перепусткою після завершення візиту?", "гостевых пропусков"),
    ("Как оформить командировку и какую отчётность нужно предоставить?", "бизнес-поездки"),
    ("Які строки зберігання персональних даних контрагентів?", "персональной информации"),
    ("Как выявляют корпоративное мошенничество?", "мошенничеству"),
    ("Як оцінюють постачальників з точки зору інформаційної безпеки?", "поставщиками"),
    ("За скільки днів приходить нагадування перед відпусткою?", "отсутствия"),
    ("Скільки днів відпустки належить за рік?", "отсутствия"),
    ("Що заборонено надсилати електронною поштою?", "ПЕРЕДАЧІ ДАНИХ"),
    ("Какие сроки начала реагирования на инциденты безопасности?", "INCIDENT MANAGEMENT"),
    ("Як повідомити клієнта про інцидент?", "сповіщення клієнтів"),
    ("Який протокол синхронізації часу використовується на серверах?", "КОНФИГУРАЦИЙ"),
    ("Когда система мониторинга автоматически создаёт заявку в тикет-системе?", "МОНИТОРИНГА"),
    ("Які вимоги до точності та актуальності даних для контрагентів?", "DATA BREACH"),
    ("Що таке середовище розробки та тестування?", "LIFE CYC"),
    ("Які цілі потрібно сформулювати при створенні навчального курсу?", "T&D"),
    ("Як призначити Placement Grammar Test співробітнику?", "PLACEMENT"),
    ("Які заявки до сервісу 1С не приймаються?", "1С"),
    ("Які статуси бувають у заявки до відділу розробки?", "відділ розробки"),
    ("Які посади у фінансовому відділі є в матриці доступів?", "Матрица"),
    ("Что нужно сделать с данными перед утилизацией оборудования?", "DATA DISPOSAL"),
    ("Чи проводить компанія аудит техніки при віддаленій роботі?", "REMOTE ACCESS"),
    ("Як часто проводиться оцінка ризиків інформаційної безпеки?", "INFORMATION SECURITY"),
    ("Які вимоги до фізичного доступу до серверного приміщення?", "PHYSICAL ACCESS"),
    ("Що робити при втраті особистого пристрою з робочими даними?", "BYOD"),
    ("Что делать с документами на столе, когда уходишь с рабочего места?", "CLEAR DESKTOP"),
    ("Як довго діють ключі шифрування?", "CRYPTOGRAPHIC"),
    ("Які порти потрібні для віддаленого доступу?", "REMOTE ACCESS"),
    # документи, додані після розширення бази знань
    ("Які дисциплінарні заходи застосовуються до працівників?", "Disciplinary"),
    ("Що означає абревіатура TL у компанії?", "Glossary"),
    ("Що входить в обхідний лист при звільненні?", "ливера"),
    ("Як налаштувати автовідповідь у пошті на час відпустки?", "автоответа"),
    ("Як вести облік робочого часу в Toggl?", "Toggl"),
    ("Які обов'язки має Head of Recruitment?", "Head of Recruitment"),
    # питання, відповіді на які в базі немає: очікуємо чесну відмову
    ("Який рецепт борщу?", None),
    ("Скільки коштує біткоїн сьогодні?", None),
    ("Яка зараз погода у Києві?", None),
    ("Яка зарплата директора компанії?", None),
]
NOT_FOUND = "не знайшов"
TOP_SOURCES = 6
# ключовий факт, який має бути в тексті відповіді
FACTS = {'Скільки символів має бути в паролі користувача?': '12', 'Як часто потрібно змінювати пароль?': '90', 'Скільки днів відпустки належить за рік?': '20', 'За скільки днів приходить нагадування перед відпусткою?': '5', 'Як довго діють ключі шифрування?': '3', 'Какие требования к паролям сервисных аккаунтов?': '24'}


def ask(question):
    url = f"{os.environ['FLOWISE_URL'].rstrip('/')}/api/v1/prediction/{os.environ['FLOWISE_CHATFLOW_ID']}"
    body = json.dumps({"question": question,
                       "overrideConfig": {"sessionId": "eval-" + uuid.uuid4().hex[:8]}},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": "Bearer " + os.environ["FLOWISE_API_KEY"],
        "User-Agent": "curl/8.7.1",
    })
    return json.load(urllib.request.urlopen(req, timeout=120))


def main():
    ranks, answered_ok, fact_total, fact_ok, abst_total, abst_ok = [], 0, 0, 0, 0, 0
    for question, expected in CASES:
        reply = ask(question)
        text = reply.get("text") or ""
        names = [(d.get("metadata") or {}).get("fileName", "") for d in reply.get("sourceDocuments", [])][:TOP_SOURCES]
        if expected is None:
            abst_total += 1
            ok = NOT_FOUND in text
            abst_ok += ok
            print(("OK   " if ok else "FAIL ") + question + "  ->  " + ("відмова" if ok else "відповів, хоча даних немає"))
            continue
        wanted = (expected,) if isinstance(expected, str) else expected
        rank = next((i + 1 for i, n in enumerate(names) if any(w.lower() in n.lower() for w in wanted)), None)
        ranks.append(rank)
        line = f"rank={rank or '-'}"
        fact = FACTS.get(question)
        if fact:
            fact_total += 1
            good = fact in text
            fact_ok += good
            line += "  факт " + ("є" if good else "НЕМАЄ")
        answered_ok += 1 if (rank and NOT_FOUND not in text) else 0
        print(("OK   " if rank else "FAIL ") + question + "  ->  " + line)
    n = len(ranks)
    mrr = sum(1 / r for r in ranks if r) / n
    print("\nМетрики пошуку по " + str(n) + " питаннях з відповіддю:")
    print(f"  Hit@1 : {sum(1 for r in ranks if r == 1)}/{n}")
    print(f"  Hit@3 : {sum(1 for r in ranks if r and r <= 3)}/{n}")
    print(f"  Hit@{TOP_SOURCES} : {sum(1 for r in ranks if r)}/{n}")
    print(f"  MRR   : {mrr:.3f}")
    print(f"  Відповіді по суті (джерело знайдено і бот не відмовився): {answered_ok}/{n}")
    print(f"  Ключові факти у відповіді: {fact_ok}/{fact_total}")
    print(f"  Чесна відмова на питаннях без відповіді: {abst_ok}/{abst_total}")
    failed = (n - sum(1 for r in ranks if r)) + (abst_total - abst_ok)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
