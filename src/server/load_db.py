"""Load the dashboard CSVs from data/processed into PostgreSQL.

Run by refresh.sh after the leads are rebuilt, or by hand: python src/server/load_db.py [table ...]
Every table is rebuilt next to the old one and swapped in one transaction, so the app never sees a half-loaded list.
All columns are text, exactly as in the CSV: the dashboard parses them itself.
"""
import csv
import sys

from psycopg import sql

from datasets import PROCESSED, TABLES, connect

csv.field_size_limit(sys.maxsize)


def load(conn, name):
    path = PROCESSED / f"{name}.csv"
    if not path.exists():
        print(f"{name}: {path.name} not found, table left as it is")
        return
    with open(path, encoding="utf-8-sig", newline="") as f:
        first = f.readline()
        f.seek(0)
        reader = csv.reader(f, delimiter=";" if first.count(";") > first.count(",") else ",")
        header = next(reader)
        staging = sql.Identifier(name + "_new")
        columns = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(h)) for h in header)
        skipped = 0
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(staging))
            cur.execute(sql.SQL("CREATE TABLE {} (_ord integer, {})").format(staging, columns))
            with cur.copy(sql.SQL("COPY {} FROM STDIN").format(staging)) as copy:
                for i, row in enumerate(reader):
                    if not row:
                        continue
                    if len(row) != len(header):
                        skipped += 1
                        continue
                    copy.write_row([i] + [cell.replace("\x00", "") for cell in row])
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(name)))
            cur.execute(sql.SQL("ALTER TABLE {} RENAME TO {}").format(staging, sql.Identifier(name)))
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name)))
            count = cur.fetchone()[0]
    conn.commit()
    print(f"{name}: {count} rows" + (f", {skipped} malformed rows skipped" if skipped else ""))


if __name__ == "__main__":
    wanted = sys.argv[1:] or TABLES
    unknown = [t for t in wanted if t not in TABLES]
    if unknown:
        sys.exit(f"unknown table {unknown}; choose from {TABLES}")
    with connect() as conn:
        for table in wanted:
            load(conn, table)
