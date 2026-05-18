from unittest.mock import patch

from terminal.web_research import scrape_screener_in


class _Response:
    status_code = 200
    text = """
    <html><body>
      <ul id="top-ratios"><li><span class="name">Stock P/E</span><span class="number">51.8</span></li></ul>
      <section id="quarters">
        <table>
          <tr><th></th><th>Mar 2023</th><th>Jun 2023</th><th>Sep 2023</th><th>Dec 2023</th><th>Mar 2024</th><th>Jun 2024</th><th>Sep 2024</th><th>Dec 2024</th><th>Mar 2025</th><th>Jun 2025</th><th>Sep 2025</th><th>Dec 2025</th><th>Mar 2026</th></tr>
          <tr><td>Sales+</td><td>1,694</td><td>1,829</td><td>1,854</td><td>1,875</td><td>1,873</td><td>2,107</td><td>2,116</td><td>2,136</td><td>2,174</td><td>2,353</td><td>2,435</td><td>2,724</td><td>2,586</td></tr>
          <tr><td>Net Profit+</td><td>219</td><td>237</td><td>233</td><td>210</td><td>220</td><td>245</td><td>250</td><td>270</td><td>289</td><td>312</td><td>330</td><td>350</td><td>340</td></tr>
        </table>
      </section>
      <section id="profit-loss">
        <table>
          <tr><th></th><th>Dec 2022</th><th>Dec 2023</th><th>Dec 2024</th><th>Dec 2025</th><th>TTM</th></tr>
          <tr><td>Sales+</td><td>6,867</td><td>7,251</td><td>8,232</td><td>9,686</td><td>10,097</td></tr>
          <tr><td>EPS in Rs</td><td>56.25</td><td>57.52</td><td>60.07</td><td>73.60</td><td>81.25</td></tr>
          <tr><td>10 Years:</td><td>43%</td></tr>
        </table>
      </section>
    </body></html>
    """

    def raise_for_status(self):
        return None


def test_scrape_screener_in_uses_latest_quarterly_columns():
    with patch("terminal.web_research._get", return_value=_Response()):
        result = scrape_screener_in("SCHAEFFLER")

    quarterly = result["quarterly"]
    assert quarterly["_headers"] == ["Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026"]
    assert quarterly["Sales+"] == ["2,136", "2,174", "2,353", "2,435", "2,724", "2,586"]
    assert quarterly["Net Profit+"] == ["270", "289", "312", "330", "350", "340"]


def test_scrape_screener_in_annual_values_align_with_headers():
    with patch("terminal.web_research._get", return_value=_Response()):
        result = scrape_screener_in("SCHAEFFLER")

    annual = result["annual_pl"]
    assert annual["_headers"] == ["Dec 2022", "Dec 2023", "Dec 2024", "Dec 2025", "TTM"]
    assert annual["Sales+"] == ["6,867", "7,251", "8,232", "9,686", "10,097"]
    assert annual["EPS in Rs"] == ["56.25", "57.52", "60.07", "73.60", "81.25"]
    assert "10 Years:" not in annual
