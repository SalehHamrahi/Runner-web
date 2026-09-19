# Runner Tournament Platform

Runner یک پلتفرم محلی برای مدیریت تورنومنت و تحلیل مسابقات RoboCup 2D است. این پروژه از اعتبارسنجی تیم‌ها و اجرای تورنومنت تا ذخیره نتایج، پردازش فایل‌های RCG/RCL، تحلیل آماری، Replay، داشبورد وب، گزارش‌گیری، اعلان Discord و افزونه‌های اختیاری را پوشش می‌دهد.

[English](README.md) · [Quality & Release](QUALITY.md) · [راهنمای Plugin](docs/PLUGIN_API.md)

## قابلیت‌ها

- تورنومنت Round-Robin و Stepladder
- اعتبارسنجی تیم‌ها و نگهداری وضعیت در SQLite
- خواندن اطلاعات World State از RCG و Actionهای RCL
- استخراج Event، وضعیت بازیکنان، معیارهای فضایی، Possession، پاس و شوت
- تحلیل قابل تکرار در سطح مسابقه و تیم
- تحلیل‌های پیشرفته و ابزارهای شبیه‌سازی آفلاین
- داشبورد وب محلی با Replay، نمودارها و دانلود گزارش
- خروجی JSON، HTML، CSV، PDF و بسته گرافیک
- اعلان Discord به همراه تاریخچه اعلان در SQLite
- سیستم Plugin اختیاری برای Event، پایان Match و پایان Tournament
- Quality Gate و Release قابل تکرار

## نیازمندی‌ها

- Linux و Bash
- Python 3.11+
- `rcssserver` و فایل‌های تیم برای اجرای مسابقات واقعی
- بسته‌های موجود در `requirements.txt` برای تحلیل، گرافیک و Export

## نصب

```bash
cd Runner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x run.sh scripts/quality_check.sh
```

یا:

```bash
./install_requirements.sh
```

## تنظیمات

فایل اصلی تنظیمات `config.conf` است. گزینه‌های مهم:

- `type`: نوع تورنومنت (`round_robin` یا `stepladder`)
- `fullstate`: فعال بودن fullstate
- `synch_mode`: حالت synchronized سرور
- `nr_extra_halfs`: تعداد نیمه‌های اضافه
- `penalty_shoot_outs`: استفاده از پنالتی در صورت فعال بودن
- `data_collection`: ذخیره اطلاعات Match
- `analytics_enabled`: اجرای خودکار Analytics
- `spatial_grid_x` و `spatial_grid_y`: دقت شبکه تحلیل فضایی
- `discord_enabled`: فعال بودن Discord
- `discord_webhook_url`: آدرس Webhook؛ متغیر محیطی اولویت دارد
- `plugins_enabled`: اجرای خودکار Hookهای Plugin
- `plugins_dir`: مسیر Pluginها

برای Webhook واقعی بهتر است از متغیر محیطی استفاده شود:

```bash
export RUNNER_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
```

## تیم‌ها

نام تیم‌ها را هر کدام در یک خط در `teams.txt` قرار دهید و پوشه/فایل مربوط به آن‌ها را در `Bins/` قرار دهید. سپس:

```bash
python3 runner.py validate
```

## اجرای تورنومنت

برای اجرای تعاملی:

```bash
./run.sh
```

یا از CLI:

```bash
python3 runner.py run --type round_robin
python3 runner.py run --type stepladder
```

اسکریپت‌های `Group_tournament.sh` و `Stepladder_tournament.sh` نیز گردش کامل اجرای Match، مدیریت سرور، فایل‌های Log و پردازش بعد از مسابقه را انجام می‌دهند.

## چرخه Match و تحلیل

```bash
python3 runner.py begin
python3 runner.py start-match TeamA TeamB 1
python3 runner.py finish-match-rcg 1 --rcg-file ./match.rcg
python3 runner.py ingest-match 1 --rcg-file ./match.rcg --rcl-file ./match.rcl
python3 runner.py analyze-match 1
python3 runner.py analyze-advanced 1
```

## گزارش و داشبورد

```bash
python3 runner.py export-match 1 --format pdf
python3 runner.py export-tournament TOURNAMENT_ID --format html
python3 runner.py web
```

داشبورد روی `http://127.0.0.1:8000` در دسترس است و خلاصه تورنومنت، Matchها، Replay، تحلیل، گزارش و Notification History را نمایش می‌دهد.

## Discord

تاریخچه اعلان‌ها:

```bash
python3 runner.py notifications --limit 50
```

ارسال Discord در Process جدا انجام می‌شود و نتیجه آن در SQLite با وضعیت `pending`، `sent` یا `failed` ثبت می‌شود.

## Plugin System

Pluginها فایل‌های Python ساده‌ای هستند که داخل مسیر `plugins_dir` قرار می‌گیرند. برای امنیت، اجرای خودکار Pluginها پیش‌فرض خاموش است.

نمونه:

```python
PLUGIN = {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "My Runner integration",
    "hooks": ["on_match_finished"],
}

def on_match_finished(context):
    print(f"Match {context['match_id']} finished")
    return {"ok": True}
```

Hookهای فعلی:

- `on_event`
- `on_match_finished`
- `on_tournament_finished`

اجرای یک Hook توسط Pluginها باعث توقف Runner نمی‌شود و خطاهای Plugin جداگانه ثبت می‌شوند. برای جزئیات به [docs/PLUGIN_API.md](docs/PLUGIN_API.md) مراجعه کنید.

دستورات مدیریت:

```bash
python3 runner.py plugins list
python3 runner.py plugins info my-plugin
python3 runner.py plugins run on_match_finished --payload '{"match_id":1}'
```

## کیفیت و Release

```bash
./scripts/quality_check.sh
make release
```

Release محلی، Database، Log، RCG/RCL، گزارش‌های تولیدشده و Credentialها را وارد بسته نهایی نمی‌کند و سلامت ZIP را بررسی می‌کند.

## ساختار پروژه

```text
Runner/
├── Analyzer/          # گرافیک و ابزارهای تحلیل
├── Bins/              # تیم‌ها
├── core/              # منطق اصلی، DB، تحلیل، گزارش و Plugin
├── docs/              # مستندات توسعه و Integration
├── plugins/           # Pluginهای اختیاری
├── scripts/           # Quality و Release
├── tests/             # تست‌ها
├── web/               # داشبورد وب
├── config.conf       # تنظیمات
├── teams.txt         # لیست تیم‌ها
├── runner.py         # CLI اصلی
└── run.sh            # Launcher
```

## نویسندگان

- [Soroush Mazloum](https://github.com/SoroushMazloum)
- [Saleh Hamrahi](https://github.com/SalehHamrahi)

## مجوز

پیش از استفاده یا انتشار پروژه فایل [LICENSE](LICENSE) را مطالعه کنید.
