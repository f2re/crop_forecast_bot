# Audit validation gate

Этот файл фиксирует обязательный повторный CI после сквозного scientific/data-quality remediation.

Проверка должна подтвердить:

- source-aware разделение reanalysis / operational past / forecast;
- отсутствие фиктивных нулей при пропусках ET₀ и осадков;
- исключение прогнозных строк из ГТК;
- использование только forecast-строк для frost screening;
- отсутствие synthetic ML training в production runtime;
- зелёные ruff, compileall, pytest и Bash/shellcheck.
