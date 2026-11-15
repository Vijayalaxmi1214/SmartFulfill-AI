
from database.db_manager import get_connection


def get_fulfillment_kpis(connection):
    """Calculate overall fulfillment performance."""

    shipment_data = connection.execute(
        """
        SELECT
            COUNT(*) AS total_shipments,
            SUM(CASE WHEN shipment_status = 'DELIVERED'
                THEN 1 ELSE 0 END) AS delivered,
            SUM(CASE WHEN shipment_status = 'FAILED'
                THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN shipment_status = 'IN_TRANSIT'
                THEN 1 ELSE 0 END) AS in_transit
        FROM shipments
        """
    ).fetchone()

    exception_data = connection.execute(
        """
        SELECT
            COUNT(*) AS total_exceptions,
            SUM(CASE WHEN exception_status = 'OPEN'
                THEN 1 ELSE 0 END) AS open_exceptions,
            SUM(CASE WHEN issue_type = 'DELIVERY_DELAYED'
                THEN 1 ELSE 0 END) AS delayed,
            SUM(CASE WHEN issue_type = 'DELIVERY_FAILED'
                THEN 1 ELSE 0 END) AS failed_deliveries
        FROM tracking_exceptions
        """
    ).fetchone()

    total = shipment_data["total_shipments"] or 0
    delivered = shipment_data["delivered"] or 0

    delivery_rate = (
        round((delivered / total) * 100, 2)
        if total else 0
    )

    return {
        "total_shipments": total,
        "delivered": delivered,
        "failed": shipment_data["failed"] or 0,
        "in_transit": shipment_data["in_transit"] or 0,
        "delivery_rate": delivery_rate,
        "total_exceptions": exception_data["total_exceptions"] or 0,
        "open_exceptions": exception_data["open_exceptions"] or 0,
        "delayed_exceptions": exception_data["delayed"] or 0,
        "failed_exceptions": exception_data["failed_deliveries"] or 0,
    }


def get_exception_breakdown(connection):
    """Summarize exceptions by type and severity."""

    rows = connection.execute(
        """
        SELECT
            issue_type,
            severity,
            exception_status,
            COUNT(*) AS total
        FROM tracking_exceptions
        GROUP BY issue_type, severity, exception_status
        ORDER BY
            CASE severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                WHEN 'LOW' THEN 4
                ELSE 5
            END
        """
    ).fetchall()

    return [dict(row) for row in rows]


def get_prioritized_exceptions(connection):
    """List exceptions from highest to lowest priority."""

    rows = connection.execute(
        """
        SELECT
            te.tracking_exception_id,
            te.shipment_id,
            s.order_id,
            s.carrier_id,
            s.node_id,
            te.issue_type,
            te.severity,
            te.expected_delivery_date,
            te.actual_delivery_date,
            te.details,
            te.exception_status,
            te.created_at
        FROM tracking_exceptions te
        JOIN shipments s
            ON s.shipment_id = te.shipment_id
        ORDER BY
            CASE te.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                WHEN 'LOW' THEN 4
                ELSE 5
            END,
            te.created_at DESC
        """
    ).fetchall()

    return [dict(row) for row in rows]


def generate_business_insights(kpis, breakdown):
    """Generate understandable business recommendations."""

    insights = []

    if kpis["failed_exceptions"] > 0:
        insights.append(
            "Investigate failed deliveries and review carrier "
            "delivery-attempt performance."
        )

    if kpis["delayed_exceptions"] > 0:
        insights.append(
            "Review delayed shipments and identify opportunities "
            "to improve delivery promises."
        )

    if kpis["open_exceptions"] > 0:
        insights.append(
            "Prioritize open exceptions and assign them for "
            "operational follow-up."
        )

    if kpis["delivery_rate"] < 90:
        insights.append(
            "Delivery success is below 90%. Review fulfillment "
            "and carrier operations."
        )
    elif kpis["total_shipments"] > 0:
        insights.append(
            "Delivery success is at least 90%. Continue monitoring "
            "shipment performance."
        )

    critical_count = sum(
        item["total"]
        for item in breakdown
        if item["severity"] == "CRITICAL"
    )

    if critical_count > 0:
        insights.append(
            "Critical-severity exceptions require immediate attention."
        )

    if not insights:
        insights.append(
            "No major fulfillment issues were detected."
        )

    return insights


def run_exception_intelligence():
    """Run the Stage 6 analytics engine."""

    connection = get_connection()

    try:
        kpis = get_fulfillment_kpis(connection)
        breakdown = get_exception_breakdown(connection)
        prioritized = get_prioritized_exceptions(connection)
        insights = generate_business_insights(kpis, breakdown)

        print("\n" + "=" * 55)
        print("SMARTFULFILL AI - EXCEPTION INTELLIGENCE")
        print("=" * 55)

        print("\nFULFILLMENT KPIs")
        print("-" * 35)

        for key, value in kpis.items():
            print("{}: {}".format(key.replace("_", " ").title(), value))

        print("\nEXCEPTION BREAKDOWN")
        print("-" * 35)

        for item in breakdown:
            print(
                "{} | {} | {} | {}".format(
                    item["issue_type"],
                    item["severity"],
                    item["exception_status"],
                    item["total"],
                )
            )

        print("\nTOP PRIORITY EXCEPTIONS")
        print("-" * 35)

        for item in prioritized[:10]:
            print(
                "{} | {} | {} | Shipment: {}".format(
                    item["severity"],
                    item["issue_type"],
                    item["exception_status"],
                    item["shipment_id"],
                )
            )

        print("\nBUSINESS INSIGHTS")
        print("-" * 35)

        for number, insight in enumerate(insights, start=1):
            print("{}. {}".format(number, insight))

        print("\nSTAGE 6 ANALYTICS COMPLETED")

        return {
            "kpis": kpis,
            "breakdown": breakdown,
            "prioritized_exceptions": prioritized,
            "insights": insights,
        }

    finally:
        connection.close()
