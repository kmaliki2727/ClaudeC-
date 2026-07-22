"""Interactive correlation matrix for the Group SIPP holdings, built from yfinance price data."""

import argparse

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

TICKERS = {
    "AAPL": "Apple",
    "GOOG": "Alphabet",
    "META": "Meta Platforms",
    "V": "Visa",
    "BRK-B": "Berkshire Hathaway",
    "AMZN": "Amazon",
    "BABA": "Alibaba",
    "XDW0.L": "Xtrackers World Energy",
    "SGLP.L": "Invesco Physical Gold",
    "IASH.L": "iShares MSCI China A",
    "XDWF.L": "Xtrackers World Financials",
    "XDWT.L": "Xtrackers World IT",
    "XDWM.L": "Xtrackers World Materials",
    "XWTS.L": "Xtrackers World Comm. Services",
    "VFEM.L": "Vanguard FTSE Emerging Markets",
    "XDWH.L": "Xtrackers World Health Care",
    "XDWI.L": "Xtrackers World Industrials",
    "XDWS.L": "Xtrackers World Consumer Staples",
    "XDWC.L": "Xtrackers World Consumer Discretionary",
    "LOCK.L": "iShares Digital Security",
    "SPAG.L": "iShares Agribusiness",
}


def fetch_returns(tickers, period="1y", interval="1d"):
    prices = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False)["Close"]
    if isinstance(prices, pd.Series):
        prices = prices.to_frame(tickers[0])
    return prices.pct_change().dropna(how="all")


def build_heatmap(returns, labels, method="pearson"):
    corr = returns.corr(method=method).reindex(index=list(labels), columns=list(labels))
    names = [labels[t] for t in corr.columns]
    fig = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=names,
            y=names,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            reversescale=True,
            text=corr.round(2).values,
            texttemplate="%{text}",
            hovertemplate="%{y} vs %{x}<br>correlation: %{z:.2f}<extra></extra>",
            colorbar=dict(title="correlation"),
        )
    )
    fig.update_layout(
        title=f"Group SIPP holdings — {method.title()} correlation of daily returns",
        xaxis=dict(tickangle=45),
        width=950,
        height=950,
    )
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="*", default=list(TICKERS), help="Ticker symbols to include")
    parser.add_argument("--period", default="1y", help="yfinance period, e.g. 6mo, 1y, 5y")
    parser.add_argument("--interval", default="1d", help="yfinance interval, e.g. 1d, 1wk")
    parser.add_argument("--method", default="pearson", choices=["pearson", "spearman", "kendall"])
    parser.add_argument("--output", default="correlation_matrix.html", help="Output HTML file")
    args = parser.parse_args()

    labels = {t: TICKERS.get(t, t) for t in args.tickers}
    returns = fetch_returns(list(labels), period=args.period, interval=args.interval)
    fig = build_heatmap(returns, labels, method=args.method)
    fig.write_html(args.output, include_plotlyjs="cdn")
    print(f"Saved interactive correlation matrix to {args.output}")


if __name__ == "__main__":
    main()
