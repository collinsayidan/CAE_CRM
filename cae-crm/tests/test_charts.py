import charts


def test_stacked_bar_splits_by_share_and_escapes_titles():
    bar = str(charts.stacked_bar([(300, "var(--stage-1)", "Lead <b>"), (100, "var(--stage-2)", "Qualified"),
                                  (0, "var(--stage-3)", "Proposal")], label="Pipeline by stage"))
    assert 'role="img" aria-label="Pipeline by stage"' in bar
    assert "flex: 0.7500" in bar and "flex: 0.2500" in bar
    assert "Proposal" not in bar  # an empty stage takes no room
    assert "Lead &lt;b&gt;" in bar and "<b>" not in bar


def test_stacked_bar_with_nothing_open_is_an_empty_track():
    assert str(charts.stacked_bar([(0, "red", "Lead")], label="x")) == '<div class="stack-bar" role="img" aria-label="x"></div>'


def test_sparkline_is_a_single_line():
    svg = str(charts.sparkline([1, 3, 2]))
    assert svg.count("<path") == 1 and "spark-line" in svg
    assert charts.sparkline([5]) == ""


def test_home_shows_pipeline_as_a_bar(client):
    page = client.get("/").get_data(as_text=True)
    assert 'class="stack-bar"' in page and "donut" not in page
    assert "% of quarterly quota" in page
