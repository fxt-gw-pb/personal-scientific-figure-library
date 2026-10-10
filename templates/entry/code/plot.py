#!/usr/bin/env python3
"""Plotting interface scaffold. Implement this entry after reviewing its reference."""
import argparse


def main():
    parser = argparse.ArgumentParser(description="待实现的科研图表；应读取 CSV 和 style.yaml。")
    parser.add_argument("--data", required=True, help="CSV 输入")
    parser.add_argument("--style", required=True, help="实际使用的 YAML 样式")
    parser.add_argument("--out", required=True, help="输出目录，写入 figure.png / figure.svg / figure.pdf")
    parser.parse_args()
    raise SystemExit("此条目尚未实现。请先读取参考图和数据契约，完成参数化代码；脚手架不会生成假复现图。")


if __name__ == "__main__":
    main()
