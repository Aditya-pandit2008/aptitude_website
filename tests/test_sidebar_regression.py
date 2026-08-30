from pathlib import Path


def test_shared_sidebar_is_supported_by_mobile_nav_script():
    script_path = Path(__file__).resolve().parents[1] / 'static' / 'JS' / 'responsive.js'
    js = script_path.read_text(encoding='utf-8')

    assert '.shared-sidebar' in js
    assert "document.querySelector('.sidebar, .shared-sidebar, .admin-sidebar')" in js
