#!/usr/bin/env python3
"""
Generate Comprehensive Performance Reports from Backtest Results
Creates CSV files, HTML reports, and analysis summaries
"""

import json
import csv
from datetime import datetime
from typing import List, Dict, Any
import statistics

def load_backtest_results() -> List[Dict]:
    """Load backtest results from JSON file"""
    with open("backtest_results_1000.json", 'r') as f:
        data = json.load(f)
    return data["results"]

def filter_realistic_results(results: List[Dict]) -> List[Dict]:
    """Filter out unrealistic results (likely due to overfitting or data issues)"""
    filtered = []
    for result in results:
        if result["status"] != "completed":
            continue
        
        # Filter criteria for realistic strategies:
        # 1. Total return between -100% and +500% (over 90 days)
        # 2. Average monthly return between -50% and +50%
        # 3. Win rate between 20% and 85%
        # 4. At least 10 trades
        # 5. Max drawdown less than 80%
        
        if (result["total_trades"] >= 10 and
            -100 <= result["total_return_pct"] <= 500 and
            -50 <= result["avg_monthly_return_pct"] <= 50 and
            20 <= result["win_rate"] <= 85 and
            result.get("max_drawdown_pct", 0) < 80):
            filtered.append(result)
    
    return filtered

def generate_csv_report(results: List[Dict], filename: str):
    """Generate CSV report with all strategy performance metrics"""
    headers = [
        "Rank", "Strategy ID", "Strategy Name", "Type", "Total Trades",
        "Win Rate %", "Total Return %", "Avg Monthly Return %", "Median Monthly Return %",
        "Profit Factor", "Avg Win %", "Avg Loss %", "Max Drawdown %",
        "Sharpe Ratio", "Final Capital", "Avg Trade Duration"
    ]
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        for rank, result in enumerate(results, 1):
            writer.writerow([
                rank,
                result["strategy_id"],
                result["strategy_name"],
                result["strategy_type"],
                result["total_trades"],
                result["win_rate"],
                result["total_return_pct"],
                result["avg_monthly_return_pct"],
                result.get("median_monthly_return_pct", 0),
                result.get("profit_factor", 0),
                result.get("avg_win_pct", 0),
                result.get("avg_loss_pct", 0),
                result.get("max_drawdown_pct", 0),
                result.get("sharpe_ratio", 0),
                result.get("final_capital", 10000),
                result.get("avg_trade_duration", 0)
            ])
    
    print(f"✓ Generated CSV report: {filename}")

def generate_monthly_returns_csv(results: List[Dict], filename: str):
    """Generate CSV with month-by-month returns for all strategies"""
    # Collect all unique months
    all_months = set()
    for result in results:
        if "monthly_returns" in result:
            all_months.update(result["monthly_returns"].keys())
    
    months = sorted(list(all_months))
    
    headers = ["Strategy ID", "Strategy Name", "Type"] + months + ["Avg Monthly %"]
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        for result in results[:200]:  # Top 200 strategies
            row = [
                result["strategy_id"],
                result["strategy_name"],
                result["strategy_type"]
            ]
            
            monthly_data = result.get("monthly_returns", {})
            for month in months:
                row.append(round(monthly_data.get(month, 0), 2))
            
            row.append(result["avg_monthly_return_pct"])
            writer.writerow(row)
    
    print(f"✓ Generated monthly returns CSV: {filename}")

def generate_html_report(results: List[Dict], filename: str):
    """Generate HTML report with interactive tables"""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy Backtest Results - Top 100</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
        }
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .summary-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        .summary-box h3 {
            margin: 0 0 10px 0;
            font-size: 14px;
            opacity: 0.9;
        }
        .summary-box p {
            margin: 0;
            font-size: 28px;
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }
        th {
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            position: sticky;
            top: 0;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        tr:hover {
            background-color: #f8f9fa;
        }
        .positive {
            color: #27ae60;
            font-weight: bold;
        }
        .negative {
            color: #e74c3c;
            font-weight: bold;
        }
        .rank {
            font-weight: bold;
            color: #3498db;
        }
        .type-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            color: white;
        }
        .type-momentum { background-color: #3498db; }
        .type-mean_reversion { background-color: #9b59b6; }
        .type-breakout { background-color: #e74c3c; }
        .type-btc_correlation { background-color: #f39c12; }
        .type-volume_based { background-color: #1abc9c; }
        .type-volatility { background-color: #e67e22; }
        .type-macd { background-color: #34495e; }
        .type-hybrid { background-color: #16a085; }
        .type-scalping { background-color: #c0392b; }
        .type-swing { background-color: #27ae60; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Strategy Backtest Results - Top 100 Performers</h1>
        <p style="color: #7f8c8d; margin-bottom: 20px;">
            Backtested on synthetic data | Initial Capital: $10,000 | Period: ~90 days
        </p>
"""
    
    # Calculate summary statistics
    avg_monthly = statistics.mean([r["avg_monthly_return_pct"] for r in results[:100]])
    median_monthly = statistics.median([r["avg_monthly_return_pct"] for r in results[:100]])
    avg_win_rate = statistics.mean([r["win_rate"] for r in results[:100]])
    total_strategies = len(results)
    
    html += f"""
        <div class="summary">
            <div class="summary-box">
                <h3>Total Strategies Tested</h3>
                <p>{total_strategies}</p>
            </div>
            <div class="summary-box">
                <h3>Avg Monthly Return</h3>
                <p>{avg_monthly:.2f}%</p>
            </div>
            <div class="summary-box">
                <h3>Median Monthly Return</h3>
                <p>{median_monthly:.2f}%</p>
            </div>
            <div class="summary-box">
                <h3>Avg Win Rate</h3>
                <p>{avg_win_rate:.1f}%</p>
            </div>
        </div>
        
        <h2>📊 Top 100 Strategies by Average Monthly Return</h2>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Strategy Name</th>
                    <th>Type</th>
                    <th>Avg Monthly %</th>
                    <th>Total Return %</th>
                    <th>Win Rate %</th>
                    <th>Trades</th>
                    <th>Profit Factor</th>
                    <th>Max DD %</th>
                    <th>Sharpe</th>
                </tr>
            </thead>
            <tbody>
"""
    
    for rank, result in enumerate(results[:100], 1):
        monthly_class = "positive" if result["avg_monthly_return_pct"] > 0 else "negative"
        total_class = "positive" if result["total_return_pct"] > 0 else "negative"
        
        strategy_type = result["strategy_type"]
        
        html += f"""
                <tr>
                    <td class="rank">#{rank}</td>
                    <td>{result["strategy_name"]}</td>
                    <td><span class="type-badge type-{strategy_type}">{strategy_type}</span></td>
                    <td class="{monthly_class}">{result["avg_monthly_return_pct"]:.2f}%</td>
                    <td class="{total_class}">{result["total_return_pct"]:.2f}%</td>
                    <td>{result["win_rate"]:.1f}%</td>
                    <td>{result["total_trades"]}</td>
                    <td>{result.get("profit_factor", 0):.2f}</td>
                    <td>{result.get("max_drawdown_pct", 0):.1f}%</td>
                    <td>{result.get("sharpe_ratio", 0):.2f}</td>
                </tr>
"""
    
    html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    
    with open(filename, 'w') as f:
        f.write(html)
    
    print(f"✓ Generated HTML report: {filename}")

def generate_type_analysis(results: List[Dict]) -> Dict[str, Dict]:
    """Analyze performance by strategy type"""
    type_stats = {}
    
    for result in results:
        strategy_type = result["strategy_type"]
        
        if strategy_type not in type_stats:
            type_stats[strategy_type] = {
                "count": 0,
                "monthly_returns": [],
                "total_returns": [],
                "win_rates": [],
                "profit_factors": [],
                "trade_counts": []
            }
        
        stats = type_stats[strategy_type]
        stats["count"] += 1
        stats["monthly_returns"].append(result["avg_monthly_return_pct"])
        stats["total_returns"].append(result["total_return_pct"])
        stats["win_rates"].append(result["win_rate"])
        stats["profit_factors"].append(result.get("profit_factor", 0))
        stats["trade_counts"].append(result["total_trades"])
    
    # Calculate averages
    analysis = {}
    for strategy_type, stats in type_stats.items():
        analysis[strategy_type] = {
            "count": stats["count"],
            "avg_monthly_return": round(statistics.mean(stats["monthly_returns"]), 2),
            "median_monthly_return": round(statistics.median(stats["monthly_returns"]), 2),
            "avg_total_return": round(statistics.mean(stats["total_returns"]), 2),
            "avg_win_rate": round(statistics.mean(stats["win_rates"]), 2),
            "avg_profit_factor": round(statistics.mean(stats["profit_factors"]), 2),
            "avg_trades": round(statistics.mean(stats["trade_counts"]), 1)
        }
    
    return analysis

def print_summary_report(results: List[Dict], type_analysis: Dict):
    """Print comprehensive summary to console"""
    print("\n" + "=" * 100)
    print(" " * 30 + "BACKTEST RESULTS SUMMARY")
    print("=" * 100)
    
    print(f"\nTotal Strategies Analyzed: {len(results)}")
    print(f"Initial Capital per Strategy: $10,000")
    print(f"Backtest Period: ~90 days")
    
    print("\n" + "-" * 100)
    print("TOP 20 STRATEGIES BY AVERAGE MONTHLY RETURN")
    print("-" * 100)
    print(f"{'Rank':<6} {'Strategy Name':<45} {'Type':<18} {'Avg Mo %':<12} {'Total %':<12} {'Win %':<10} {'Trades'}")
    print("-" * 100)
    
    for rank, result in enumerate(results[:20], 1):
        print(f"{rank:<6} {result['strategy_name'][:44]:<45} {result['strategy_type']:<18} "
              f"{result['avg_monthly_return_pct']:>10.2f}% {result['total_return_pct']:>10.2f}% "
              f"{result['win_rate']:>8.1f}% {result['total_trades']:>6}")
    
    print("\n" + "-" * 100)
    print("PERFORMANCE BY STRATEGY TYPE")
    print("-" * 100)
    print(f"{'Type':<20} {'Count':<8} {'Avg Monthly %':<15} {'Median Monthly %':<18} {'Avg Win Rate %':<16} {'Avg Trades'}")
    print("-" * 100)
    
    # Sort by average monthly return
    sorted_types = sorted(type_analysis.items(), key=lambda x: x[1]["avg_monthly_return"], reverse=True)
    
    for strategy_type, stats in sorted_types:
        print(f"{strategy_type:<20} {stats['count']:<8} {stats['avg_monthly_return']:>13.2f}% "
              f"{stats['median_monthly_return']:>16.2f}% {stats['avg_win_rate']:>14.2f}% {stats['avg_trades']:>11.1f}")
    
    print("\n" + "=" * 100)

def main():
    """Main execution"""
    print("\n" + "=" * 100)
    print(" " * 35 + "PERFORMANCE REPORT GENERATOR")
    print("=" * 100)
    
    # Load results
    print("\nLoading backtest results...")
    all_results = load_backtest_results()
    print(f"✓ Loaded {len(all_results)} backtest results")
    
    # Filter realistic results
    print("\nFiltering for realistic strategies...")
    filtered_results = filter_realistic_results(all_results)
    print(f"✓ Filtered to {len(filtered_results)} realistic strategies")
    
    # Sort by average monthly return
    filtered_results.sort(key=lambda x: x["avg_monthly_return_pct"], reverse=True)
    
    # Generate reports
    print("\nGenerating reports...")
    generate_csv_report(filtered_results, "backtest_results_all.csv")
    generate_monthly_returns_csv(filtered_results, "backtest_monthly_returns.csv")
    generate_html_report(filtered_results, "backtest_results_report.html")
    
    # Generate type analysis
    type_analysis = generate_type_analysis(filtered_results)
    
    # Print summary
    print_summary_report(filtered_results, type_analysis)
    
    print("\n" + "=" * 100)
    print("✓ REPORT GENERATION COMPLETE")
    print("=" * 100)
    print("\nGenerated files:")
    print("  • backtest_results_all.csv - All strategy metrics")
    print("  • backtest_monthly_returns.csv - Month-by-month returns (top 200)")
    print("  • backtest_results_report.html - Interactive HTML report (top 100)")
    print("\nOpen backtest_results_report.html in a browser to view the interactive report.")
    print("=" * 100)

if __name__ == "__main__":
    main()
