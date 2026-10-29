import pytest
from hypothesis import given
from hypothesis import strategies as st

from buildreport.expr import (
    Bin,
    ExprError,
    Neg,
    Num,
    Ref,
    Sum,
    change_excel,
    compile_metrics,
    evaluate,
    measures,
    parse,
    references,
    to_excel,
)

MEASURES = {
    "net_sales_eur",
    "units_sold",
    "waste_units",
    "waste_eur",
    "labour_hours",
    "labour_cost_eur",
    "transactions",
}
METRICS = {
    "revenue": "sum(net_sales_eur)",
    "transactions": "sum(transactions)",
    "avg_basket": "revenue / transactions",
    "units_sold": "sum(units_sold)",
    "waste_eur": "sum(waste_eur)",
    "waste_pct": "waste_eur / revenue",
    "labour_hours": "sum(labour_hours)",
    "labour_cost": "sum(labour_cost_eur)",
    "labour_pct": "labour_cost / revenue",
    "revenue_per_labour_hour": "revenue / labour_hours",
}
# Branches total row 16 of the spec: metric -> column
COLUMNS = {
    "revenue": "D",
    "transactions": "G",
    "avg_basket": "H",
    "waste_eur": "I",
    "waste_pct": "J",
    "labour_hours": "K",
    "labour_cost": "L",
    "labour_pct": "M",
    "revenue_per_labour_hour": "N",
}


def test_parse_builds_nodes():
    assert parse("sum(net_sales_eur)") == Sum("net_sales_eur")
    assert parse("revenue / transactions") == Bin("/", Ref("revenue"), Ref("transactions"))
    assert parse("-2 * (a + 1)") == Bin("*", Neg(Num(2.0)), Bin("+", Ref("a"), Num(1.0)))


@pytest.mark.parametrize(
    "text",
    [
        "revenue ** 2",
        "revenue % 2",
        "revenue // 2",
        "abs(revenue)",
        "sum(revenue, units)",
        "sum(1)",
        "sum(x=1)",
        "revenue.real",
        "revenue[0]",
        "revenue if units else 0",
        "revenue > 1",
        "'text'",
        "True",
        "+revenue",
        "revenue;",
        "__import__('os')",
        "lambda: 1",
    ],
)
def test_nodes_outside_the_allow_list_are_rejected(text):
    with pytest.raises(ExprError):
        parse(text)


def test_references_and_measures():
    node = parse("(sum(waste_eur) + waste_extra) / revenue")
    assert references(node) == {"waste_extra", "revenue"}
    assert measures(node) == {"waste_eur"}


def test_evaluate_arithmetic_and_blank_propagation():
    sums = {"net_sales_eur": 200.0, "transactions": 0.0}.__getitem__
    values = {"revenue": 200.0, "blank": None, "zero": 0.0}.__getitem__
    assert evaluate(parse("sum(net_sales_eur) * 2 - 50"), sums, values) == 350.0
    assert evaluate(parse("revenue / zero"), sums, values) is None
    assert evaluate(parse("revenue / sum(transactions)"), sums, values) is None
    assert evaluate(parse("blank + 1"), sums, values) is None
    assert evaluate(parse("-blank"), sums, values) is None
    assert evaluate(parse("-(revenue / 4)"), sums, values) == -50.0


LEAVES = st.integers(min_value=-9, max_value=9).map(str) | st.sampled_from(["a", "b"])
EXPRESSIONS = st.recursive(
    LEAVES,
    lambda inner: st.tuples(inner, st.sampled_from(["+", "-", "*"]), inner).map(
        lambda t: f"({t[0]} {t[1]} {t[2]})"
    ),
    max_leaves=8,
)


@given(EXPRESSIONS, st.integers(min_value=-5, max_value=5), st.integers(min_value=-5, max_value=5))
def test_evaluate_matches_python_arithmetic(text, a, b):
    values = {"a": float(a), "b": float(b)}
    result = evaluate(parse(text), lambda measure: 0.0, values.__getitem__)
    assert result == eval(text, {"__builtins__": {}}, {"a": a, "b": b})


def test_the_committed_metrics_compile_in_order():
    compiled = compile_metrics(METRICS, MEASURES)
    assert list(compiled) == list(METRICS)
    assert compiled["waste_pct"] == Bin("/", Ref("waste_eur"), Ref("revenue"))


def test_unknown_name_is_rejected():
    with pytest.raises(ExprError, match="unknown name 'profit'"):
        compile_metrics({"revenue": "sum(net_sales_eur)", "margin": "profit / revenue"}, MEASURES)


def test_a_metric_referring_to_a_later_one_is_rejected():
    with pytest.raises(ExprError, match="avg_basket: transactions must be defined above avg_basket"):
        compile_metrics(
            {
                "revenue": "sum(net_sales_eur)",
                "avg_basket": "revenue / transactions",
                "transactions": "sum(transactions)",
            },
            MEASURES,
        )


def test_sum_needs_a_measure():
    with pytest.raises(ExprError, match=r"sum\(revenue\) names no measure"):
        compile_metrics({"revenue": "sum(revenue)"}, MEASURES)


def test_excel_translation_of_the_branches_total_row():
    compiled = compile_metrics(METRICS, MEASURES)

    def cell(name):
        return f"{COLUMNS[name]}16"

    def no_sum(measure):
        raise KeyError(measure)

    assert to_excel(compiled["avg_basket"], cell, no_sum) == 'IF(G16=0,"",D16/G16)'
    assert to_excel(compiled["waste_pct"], cell, no_sum) == 'IF(D16=0,"",I16/D16)'
    assert to_excel(compiled["labour_pct"], cell, no_sum) == 'IF(D16=0,"",L16/D16)'
    assert to_excel(compiled["revenue_per_labour_hour"], cell, no_sum) == 'IF(K16=0,"",D16/K16)'
    assert to_excel(compiled["revenue"], cell, lambda measure: "SUM(D4:D15)") == "SUM(D4:D15)"


@pytest.mark.parametrize(
    ("text", "formula"),
    [
        ("a - (b - c)", "A1-(B1-C1)"),
        ("(a + b) * c", "(A1+B1)*C1"),
        ("a + b * c", "A1+B1*C1"),
        ("-(a + b)", "-(A1+B1)"),
        ("a / (b + c)", 'IF((B1+C1)=0,"",A1/(B1+C1))'),
        ("a * 0.5 + 2", "A1*0.5+2"),
    ],
)
def test_excel_translation_keeps_precedence(text, formula):
    cells = {"a": "A1", "b": "B1", "c": "C1"}
    assert to_excel(parse(text), cells.__getitem__, cells.__getitem__) == formula


def test_change_formulas():
    assert change_excel("D16", "E16", "relative") == 'IF(E16=0,"",D16/E16-1)'
    assert change_excel("C8", "D8", "points") == 'IF(OR(C8="",D8=""),"",(C8-D8)*100)'
