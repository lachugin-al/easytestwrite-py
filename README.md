# Mobile Automation (pytest + Appium v3 + Poetry)

```markdown
# Линт с авто-починкой (включая сортировку импортов)
poetry run ruff check . --fix

# Линт (быстрая проверка, ничего не правит)
poetry run ruff check .

# Форматирование кода (детерминированно)
poetry run black .

# Только проверка форматирования (для CI)
poetry run black --check .

# Только проверка импортов isort (мы дублируем это в CI)
poetry run isort --check-only .

# Сортировка импортов (если отдельно от ruff)
poetry run isort .

# Статическая типизация
poetry run mypy src tests

# Запуск unit тестов
poetry run pytest tests/unit -q

# Coverage
poetry run pytest tests/unit \
--cov=mobiauto \
--cov-report=term-missing \
--cov-report=html:.coverage_html

# Запуск Android тестов
poetry run pytest tests/e2e/test_smoke.py \
--config configs/android.yaml \
--platform android \
-m "smoke and android"

# Запуск iOS тестов
poetry run pytest tests/e2e/test_smoke.py \
--config configs/ios.yaml \
--platform ios \
-m "smoke and ios"
```
