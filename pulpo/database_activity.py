"""Ephemeral SQL telemetry on the canonical owner's existing connection.

Counts completed SELECT and write-statement calls, not rows, bytes or fsyncs.
No SQL text, parameters, credentials or canonical evidence are retained.
"""
import sqlite3
import uuid


class ObservedConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.activity_id = uuid.uuid4().hex
        self.activity = dict(reads=0, writes=0, commits=0, rollbacks=0, errors=0)

    def _execute(self, method, sql, parameters):
        before = self.in_transaction
        word = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        try:
            result = method(sql, parameters)
        except sqlite3.Error:
            self.activity["errors"] += 1
            raise
        if word == "SELECT":
            self.activity["reads"] += 1
        elif word in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"}:
            self.activity["writes"] += 1
        elif before and not self.in_transaction and word in {"COMMIT", "END", "ROLLBACK"}:
            self.activity["rollbacks" if word == "ROLLBACK" else "commits"] += 1
        return result

    def execute(self, sql, parameters=()):
        return self._execute(super().execute, sql, parameters)

    def executemany(self, sql, parameters):
        # One completed batch call, not the number of affected rows.
        return self._execute(super().executemany, sql, parameters)

    def commit(self):
        return self._finish(super().commit, "commits")

    def rollback(self):
        return self._finish(super().rollback, "rollbacks")

    def _finish(self, method, counter):
        before = self.in_transaction
        try:
            result = method()
        except sqlite3.Error:
            self.activity["errors"] += 1
            raise
        if before:
            self.activity[counter] += 1
        return result

    def __exit__(self, kind, value, traceback):
        before = self.in_transaction
        try:
            result = super().__exit__(kind, value, traceback)
        except sqlite3.Error:
            self.activity["errors"] += 1
            if before and not self.in_transaction:
                self.activity["rollbacks"] += 1
            raise
        if before:
            self.activity["commits" if kind is None else "rollbacks"] += 1
        return result
