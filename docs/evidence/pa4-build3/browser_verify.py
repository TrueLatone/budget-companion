from datetime import datetime
import json
from pathlib import Path
import sys
import subprocess
import tempfile
from threading import Thread

sys.path.insert(0, str(Path.cwd()))
from flask_migrate import upgrade
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.extensions import db
from app.models import AssignedExpenseTask, BudgetPlan, ExpenseRecord

out = Path('docs/evidence/pa4-build3')
out.mkdir(parents=True, exist_ok=True)
results = []
with tempfile.TemporaryDirectory(prefix='pa4-browser-') as temp:
    application = create_app({'TESTING': True, 'SECRET_KEY': 'pa4-browser-only',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(temp) / 'browser.sqlite').as_posix()})
    with application.app_context():
        upgrade()
    server = make_server('127.0.0.1', 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
            results.append({'check':'environment', 'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                'date':'2026-11-26', 'browser':browser.version, 'timezone':'Asia/Bangkok', 'database':'disposable SQLite'})
            context = browser.new_context(viewport={'width':1440, 'height':1000}, timezone_id='Asia/Bangkok')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/register')
            page.locator('[name=email]').fill('pa4-browser@example.com')
            page.locator('[name=password]').fill('pa4-browser-password')
            page.locator('[name=confirm_password]').fill('pa4-browser-password')
            page.locator('form:has([name=email]) [type=submit]').click()
            page.wait_for_url('**/login')
            page.locator('[name=email]').fill('pa4-browser@example.com')
            page.locator('[name=password]').fill('pa4-browser-password')
            page.locator('form:has([name=email]) [type=submit]').click()
            page.wait_for_load_state('networkidle')
            page.goto(base + '/budget-periods/new')
            # Client date, not the host's local date.
            page.locator('[name=month]').fill('11/2026')
            page.locator('[name=tracking_start_day]').fill('26')
            page.locator('[name=available_vnd]').fill('7000000')
            page.locator('form:has([name=month]) [type=submit]').click()
            page.wait_for_url('**/budget-periods')
            page.goto(base + '/budget')
            page.locator('#add-expense summary').click()
            page.locator('[name=expense_name]').fill('Entertainment')
            page.locator('[name=priority]').select_option('P2')
            page.locator('[name=estimated_amount]').fill('200000')
            page.locator('button[formaction$="/expenses/new"]').click()
            page.wait_for_load_state('networkidle')
            assert 'Entertainment' in page.locator('table').text_content()
            for name, amount in [('rent_estimated_amount','2000000'),('electricity_estimated_amount','200000'),
                ('water_estimated_amount','100000'),('food_minimum_amount','1200000'),('transportation_minimum_amount','200000')]:
                page.locator('[name='+name+']').fill(amount)
            page.locator('#suggested-expenses > button[type=submit]').click()
            page.wait_for_load_state('networkidle')
            assert page.locator('#compare article').count() == 3
            page.screenshot(path=str(out / 'desktop-budget.png'), full_page=True)
            results.append({'check':'desktop actual registration, period, custom expense, generation', 'result':'PASS'})
            with application.app_context():
                plan = db.session.scalar(db.select(BudgetPlan).where(BudgetPlan.plan_type=='BALANCED'))
                month_id, plan_id = str(plan.budget_month_id), str(plan.id)
            page.goto(f'{base}/budget/{month_id}/plans/{plan_id}/customize')
            edit = page.locator('input[data-minimum]').first
            edit.fill(str(int(edit.input_value()) + 10000))
            page.locator('#bp-customize button').click()
            page.wait_for_load_state('networkidle')
            page.locator('form[action$="/confirm"] button').click()
            page.wait_for_url('**/expenses?**')
            with application.app_context():
                tasks = list(db.session.scalars(db.select(AssignedExpenseTask)))
                assert tasks and not list(db.session.scalars(db.select(ExpenseRecord)))
                first = next(t for t in tasks if t.allocation.budget_expense.expense_name=='Food')
                task_id = str(first.id)
            page.goto(base + '/expenses?view=day&date=2026-11-26')
            page.set_viewport_size({'width':390,'height':844})
            page.locator('[data-bs-target="#checkin'+task_id+'"]').click()
            modal=page.locator('[id="checkin'+task_id+'"]')
            modal.locator('[name=action][value=actual]').check()
            modal.locator('[name=amount]').fill('12785')
            modal.locator('[type=submit]').click()
            page.wait_for_load_state('networkidle')
            with application.app_context():
                assert db.session.scalar(db.select(db.func.sum(ExpenseRecord.amount))) == 12785
            page.goto(base+'/expenses/history?start=2026-11-01&end=2026-11-30')
            assert page.locator('input[name=amount][value="12785"]').count() > 0
            page.goto(base + '/expenses?view=day&date=2026-11-26')
            page.wait_for_timeout(500)
            page.screenshot(path=str(out / 'mobile-expenses.png'), full_page=True)
            results.append({'check':'customization, automatic schedule, mobile actual check-in and History persistence', 'result':'PASS'})
            for width,height in [(1440,1000),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                for locale in ['en','vi']:
                    for route in ['/budget','/expenses','/dashboard','/recommendations']:
                        response=page.goto(base+route+f'?budget_month_id={month_id}&lang={locale}')
                        assert response.status == 200
                        overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
                        results.append({'check':f'{route} {locale} {width}x{height}', 'result':'FAIL' if overflow else 'PASS', 'overflow':overflow})
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(base + '/dashboard?budget_month_id='+month_id+'&lang=en')
            with application.app_context():
                from app.modules.dashboard.services import build_dashboard
                from app.models import BudgetMonth
                from uuid import UUID
                period=db.session.get(BudgetMonth,UUID(month_id))
                view=build_dashboard(period.user_id,period.id)
                assert view['spent']==12785 and view['remaining'] is None
            page.screenshot(path=str(out / 'desktop-dashboard.png'), full_page=True)
            results.append({'check':'browser JavaScript runtime', 'result':'FAIL' if errors else 'PASS', 'errors':errors})
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        with application.app_context():
            db.session.remove()
            db.engine.dispose()
(out/'browser-results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
print(json.dumps(results,indent=2))
