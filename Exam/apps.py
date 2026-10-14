from flask import Flask, request, jsonify, send_from_directory
import random, time

app = Flask(__name__, static_folder=None)

@app.get("/")
def index():
    return send_from_directory(".", "indexes.html")

@app.get("/styles.css")
def styles():
    return send_from_directory(".", "styles_exam.css")


def validate_graph(n, edges, hall_limit):
    if n < 1:
        raise ValueError("N must be at least 1.")
    if hall_limit < 1:
        raise ValueError("R must be at least 1.")
    seen = set()
    for u, v in edges:
        if not (1 <= u <= n and 1 <= v <= n):
            raise ValueError(f"Course IDs must be between 1 and {n}.")
        if u == v:
            raise ValueError("A course cannot conflict with itself.")
        edge = (min(u, v), max(u, v))
        if edge in seen:
            continue
        seen.add(edge)


def adjacency_list(n, edges):
    adj = [set() for _ in range(n + 1)]
    for u, v in edges:
        if u == v:
            continue
        adj[u].add(v)
        adj[v].add(u)
    return adj


def dsatur_schedule(n, edges, hall_limit):
    """Greedy DSatur with a maximum of R courses per slot."""
    adj = adjacency_list(n, edges)
    colors = [0] * (n + 1)
    uncolored = set(range(1, n + 1))
    while uncolored:
        def priority(v):
            neighbor_colors = {colors[w] for w in adj[v] if colors[w]}
            return (len(neighbor_colors), len(adj[v]), -v)
        v = max(uncolored, key=priority)
        forbidden = {colors[w] for w in adj[v] if colors[w]}
        chosen = None
        # Try existing slots first, then open the next one.
        max_color = max(colors)
        for color in range(1, max_color + 2):
            if color not in forbidden and sum(1 for x in range(1, n + 1) if colors[x] == color) < hall_limit:
                chosen = color
                break
        if chosen is None:
            raise RuntimeError("Unable to assign a slot; check R.")
        colors[v] = chosen
        uncolored.remove(v)
    slots = {}
    for v in range(1, n + 1):
        slots.setdefault(colors[v], []).append(v)
    return {"colors": colors[1:], "slots": slots, "count": len(slots), "optimal": False}


def exact_schedule(n, edges, hall_limit, timeout_seconds=3.0):
    """
    Exact branch-and-bound search by increasing slot count.
    For practical responsiveness, instances with more than 32 courses or
    search taking over timeout_seconds are reported as not proven optimal.
    """
    adj = adjacency_list(n, edges)
    greedy = dsatur_schedule(n, edges, hall_limit)
    upper = greedy["count"]
    lower = max(1, (n + hall_limit - 1) // hall_limit)
    # Clique lower bound (greedy maximal clique heuristic).
    order = sorted(range(1, n + 1), key=lambda v: len(adj[v]), reverse=True)
    clique = []
    for v in order:
        if all(u in adj[v] for u in clique):
            clique.append(v)
    lower = max(lower, len(clique))
    if n > 32:
        return {"colors": greedy["colors"], "slots": greedy["slots"], "count": greedy["count"],
                "optimal": False, "note": "Exact search skipped for N > 32; greedy result shown."}

    deadline = time.perf_counter() + timeout_seconds
    best_colors = greedy["colors"][:]
    proven = False

    def can_color_with(limit):
        colors = [0] * (n + 1)
        slot_sizes = [0] * (limit + 1)
        uncolored = set(range(1, n + 1))
        nodes = 0

        def backtrack(colored_count):
            nonlocal nodes
            nodes += 1
            if time.perf_counter() > deadline:
                raise TimeoutError
            if colored_count == n:
                return True

            def priority(v):
                neighbor_colors = {colors[w] for w in adj[v] if colors[w]}
                return (len(neighbor_colors), len(adj[v]), -slot_sizes[0], -v)

            v = max(uncolored, key=priority)
            forbidden = {colors[w] for w in adj[v] if colors[w]}
            # Symmetry breaking: use existing colors and at most one new color.
            used_colors = max(colors)
            for color in range(1, min(limit, used_colors + 1) + 1):
                if color in forbidden or slot_sizes[color] >= hall_limit:
                    continue
                colors[v] = color
                slot_sizes[color] += 1
                uncolored.remove(v)
                if backtrack(colored_count + 1):
                    return True
                uncolored.add(v)
                slot_sizes[color] -= 1
                colors[v] = 0
            return False

        result = backtrack(0)
        return result, colors

    try:
        for slots_count in range(lower, upper + 1):
            possible, colors = can_color_with(slots_count)
            if possible:
                best_colors = colors[1:]
                upper = slots_count
                proven = True
                break
        else:
            proven = True
    except TimeoutError:
        pass

    slot_map = {}
    for course, color in enumerate(best_colors, start=1):
        slot_map.setdefault(color, []).append(course)
    return {"colors": best_colors, "slots": slot_map, "count": len(slot_map),
            "optimal": proven, "note": "" if proven else "Search time limit reached; best valid schedule shown."}


def schedule_summary(result):
    return {"colors": result["colors"], "slots": {str(k): v for k, v in result["slots"].items()},
            "count": result["count"], "optimal": result["optimal"], "note": result.get("note", "")}


@app.post("/api/schedule")
def schedule_api():
    data = request.get_json(silent=True) or {}
    try:
        n, hall_limit = int(data["n"]), int(data["r"])
        edges = [(int(e[0]), int(e[1])) for e in data.get("edges", [])]
        validate_graph(n, edges, hall_limit)
        # De-duplicate undirected edges.
        edges = sorted({(min(u, v), max(u, v)) for u, v in edges})
        started = time.perf_counter()
        greedy = dsatur_schedule(n, edges, hall_limit)
        greedy_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        exact = exact_schedule(n, edges, hall_limit)
        exact_ms = (time.perf_counter() - started) * 1000
        return jsonify({"n": n, "r": hall_limit, "edges": edges,
                        "greedy": {**schedule_summary(greedy), "time_ms": greedy_ms},
                        "exact": {**schedule_summary(exact), "time_ms": exact_ms}})
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/generate")
def generate_api():
    data = request.get_json(silent=True) or {}
    try:
        n, density, r = int(data["n"]), float(data["density"]), int(data["r"])
        if not 1 <= n <= 60:
            raise ValueError("Generated graphs require 1 ≤ N ≤ 60.")
        if not 0 <= density <= 1:
            raise ValueError("Edge density must be between 0 and 1.")
        if r < 1:
            raise ValueError("R must be at least 1.")
        rng = random.Random(data.get("seed"))
        edges = []
        for u in range(1, n + 1):
            for v in range(u + 1, n + 1):
                if rng.random() < density:
                    edges.append((u, v))
        return jsonify({"n": n, "edges": edges})
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(debug=False)
