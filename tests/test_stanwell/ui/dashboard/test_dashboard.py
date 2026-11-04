from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from stanwell.ui.dashboard import dashboard


class DummyTab:
    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


def test_main_composes_dashboard(
    monkeypatch,
):
    dashboard_arguments = Mock()

    dashboard_context = SimpleNamespace(
        has_synced_data=True,
        earliest_data=date(
            2026,
            10,
            1,
        ),
        latest_data=date(
            2026,
            10,
            27,
        ),
    )

    selected_period = SimpleNamespace(
        start=date(
            2026,
            10,
            20,
        ),
        end=date(
            2026,
            10,
            27,
        ),
    )

    period_entries = Mock()

    render_sidebar = Mock(return_value=selected_period)
    render_overview = Mock(return_value=period_entries)
    render_projects = Mock()
    render_work_patterns = Mock()
    render_tag_balances = Mock()

    monkeypatch.setattr(
        dashboard,
        "parse_dashboard_args",
        Mock(return_value=dashboard_arguments),
    )
    monkeypatch.setattr(
        dashboard,
        "create_dashboard_context",
        Mock(return_value=dashboard_context),
    )
    monkeypatch.setattr(
        dashboard,
        "render_sidebar",
        render_sidebar,
    )
    monkeypatch.setattr(
        dashboard,
        "render_overview",
        render_overview,
    )
    monkeypatch.setattr(
        dashboard,
        "render_projects",
        render_projects,
    )
    monkeypatch.setattr(
        dashboard,
        "render_work_patterns",
        render_work_patterns,
    )
    monkeypatch.setattr(
        dashboard,
        "render_tag_balances",
        render_tag_balances,
    )

    monkeypatch.setattr(
        dashboard.st,
        "set_page_config",
        Mock(),
    )
    monkeypatch.setattr(
        dashboard.st,
        "title",
        Mock(),
    )
    monkeypatch.setattr(
        dashboard.st,
        "caption",
        Mock(),
    )
    monkeypatch.setattr(
        dashboard.st,
        "tabs",
        Mock(
            return_value=[
                DummyTab(),
                DummyTab(),
                DummyTab(),
                DummyTab(),
            ]
        ),
    )

    monkeypatch.setattr(
        dashboard.sns,
        "set_theme",
        Mock(),
    )

    dashboard.main()

    render_sidebar.assert_called_once_with(dashboard_context)

    render_overview.assert_called_once_with(
        dashboard_context,
        date(2026, 10, 20),
        date(2026, 10, 27),
    )

    render_projects.assert_called_once_with(
        dashboard_context,
        date(2026, 10, 20),
        date(2026, 10, 27),
    )

    render_work_patterns.assert_called_once_with(
        dashboard_context,
        date(2026, 10, 20),
        date(2026, 10, 27),
        period_entries,
    )

    render_tag_balances.assert_called_once_with(
        dashboard_context,
        date(2026, 10, 20),
        date(2026, 10, 27),
    )
