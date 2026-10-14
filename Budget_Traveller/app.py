from flask import Flask, request, jsonify, send_from_directory
import csv, io, random, time

app = Flask(__name__, static_folder=None)

@app.get("/")
def index(): return send_from_directory(".", "index.html")
@app.get("/styles.css")
def css(): return send_from_directory(".", "styles.css")

def cheapest_route(n, edges, k, c):
    if n < 1 or k < 0 or c < 0: raise ValueError("N must be >= 1; K and C must be non-negative.")
    for u,v,p in edges:
        if not (1 <= u <= n and 1 <= v <= n): raise ValueError("Flight city IDs must be in 1..N.")
        if p < 0: raise ValueError("Flight prices must be non-negative.")
    if n == 1: return {"cost":0,"route":[1],"flights":[],"stops":0,"coupons_used":0}
    limit = k + 1
    inf = float("inf")
    dp = [[[inf]*(c+1) for _ in range(n+1)] for _ in range(limit+1)]
    parent = {}
    dp[0][1][0] = 0
    outgoing = [[] for _ in range(n+1)]
    for i,(u,v,p) in enumerate(edges): outgoing[u].append((v,p,i))
    for f in range(limit):
        for u in range(1,n+1):
            for used in range(c+1):
                base = dp[f][u][used]
                if base == inf: continue
                for v,p,idx in outgoing[u]:
                    options = [(used,p,False)]
                    if used < c: options.append((used+1,p//2,True))
                    for nu,price,coupon in options:
                        candidate = base+price
                        if candidate < dp[f+1][v][nu]:
                            dp[f+1][v][nu] = candidate
                            parent[(f+1,v,nu)] = ((f,u,used),idx,coupon)
    best = (inf,None)
    for f in range(limit+1):
        for used in range(c+1):
            if dp[f][n][used] < best[0]: best=(dp[f][n][used],(f,n,used))
    if best[1] is None: return {"cost":-1,"route":[],"flights":[],"stops":0,"coupons_used":0}
    state=best[1]; chosen=[]; cities=[n]
    while state[0] > 0:
        prev,idx,coupon=parent[state]
        u,v,p=edges[idx]
        chosen.append({"edge_index":idx,"u":u,"v":v,"price":p,"discounted_price":p//2 if coupon else p,"coupon":coupon})
        cities.append(u); state=prev
    chosen.reverse(); cities.reverse()
    return {"cost":int(best[0]),"route":cities,"flights":chosen,"stops":max(0,len(chosen)-1),
            "coupons_used":sum(f["coupon"] for f in chosen)}

def parse_csv(text):
    result=[]
    for row in csv.reader(io.StringIO(text)):
        if not row or all(not x.strip() for x in row): continue
        if row[0].strip().lower() in ("u","from","source"): continue
        if len(row)<3: raise ValueError("CSV needs columns u,v,price.")
        result.append(tuple(map(int,[x.strip() for x in row[:3]])))
    return result

@app.post("/api/solve")
def solve_api():
    d=request.get_json(silent=True) or {}
    try:
        n,k,c=int(d["n"]),int(d["k"]),int(d["c"])
        edges=[(int(e["u"]),int(e["v"]),int(e["price"])) for e in d["edges"]]
        start=time.perf_counter(); result=cheapest_route(n,edges,k,c)
        result.update({"elapsed_ms":(time.perf_counter()-start)*1000,"n":n,"m":len(edges),"k":k,"c":c,
                       "edges":[{"u":u,"v":v,"price":p,"index":i} for i,(u,v,p) in enumerate(edges)]})
        return jsonify(result)
    except (KeyError,TypeError,ValueError) as e: return jsonify({"error":str(e)}),400

@app.post("/api/parse-csv")
def parse_csv_api():
    try:
        edges=parse_csv((request.get_json(silent=True) or {}).get("csv",""))
        return jsonify({"edges":[{"u":u,"v":v,"price":p} for u,v,p in edges]})
    except ValueError as e: return jsonify({"error":str(e)}),400

@app.post("/api/generate")
def generate_api():
    d=request.get_json(silent=True) or {}
    try:
        n,k,c=int(d["n"]),int(d["k"]),int(d["c"])
        if not 2<=n<=30: raise ValueError("Generated graph N must be 2–30.")
        rng=random.Random(d.get("seed",None)); edges=[]
        for u in range(1,n): edges.append((u,u+1,rng.randint(30,240)))
        seen={(u,v) for u,v,p in edges}
        while len(edges)<min(n*2,n*(n-1)):
            u,v=rng.randint(1,n),rng.randint(1,n)
            if u!=v and (u,v) not in seen:
                seen.add((u,v)); edges.append((u,v,rng.randint(20,350)))
        return jsonify({"edges":[{"u":u,"v":v,"price":p} for u,v,p in edges]})
    except (KeyError,TypeError,ValueError) as e: return jsonify({"error":str(e)}),400

if __name__=="__main__": app.run(debug=False)
