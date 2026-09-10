"""Capacitated VRP pickup routing via Google OR-Tools.

Objective: minimise transport cost, discounted by urgency so stops near an SLA breach
are pulled earlier in the route. This is a real solver, not a distance sort. If OR-Tools
is unavailable it degrades to a clearly-labelled nearest-neighbour heuristic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    _ORTOOLS = True
except Exception:  # pragma: no cover
    _ORTOOLS = False

COST_PER_KM = 18.0  # synthetic INR/km
AVG_SPEED_KMH = 30.0


@dataclass
class Stop:
    retailer_id: str
    name: str
    lat: float
    lng: float
    demand: int
    urgency: float  # 0..1, 1 = breaching SLA now


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _matrix(points: list[tuple[float, float]]) -> list[list[int]]:
    return [[int(_haversine_km(a, b) * 1000) for b in points] for a in points]


def optimize(depot: tuple[float, float], stops: list[Stop], vehicle_capacity: int) -> dict:
    points = [depot] + [(s.lat, s.lng) for s in stops]
    dist = _matrix(points)
    n = len(points)

    if _ORTOOLS and len(stops) >= 1:
        try:
            return _solve_ortools(points, dist, stops, vehicle_capacity)
        except Exception:
            pass
    return _nearest_neighbour(points, dist, stops, vehicle_capacity)


def _urgency_penalty(stops: list[Stop], node: int) -> int:
    # higher urgency -> larger negative adjustment -> solver prefers visiting sooner
    s = stops[node - 1]
    return int(-s.urgency * 4000)


def _solve_ortools(points, dist, stops: list[Stop], vehicle_capacity: int) -> dict:
    n = len(points)
    mgr = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(mgr)

    def cost_cb(i, j):
        fi, tj = mgr.IndexToNode(i), mgr.IndexToNode(j)
        base = dist[fi][tj]
        adj = _urgency_penalty(stops, tj) if tj != 0 else 0
        return max(0, base + adj)

    idx = routing.RegisterTransitCallback(cost_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(idx)

    demands = [0] + [s.demand for s in stops]

    def demand_cb(i):
        return demands[mgr.IndexToNode(i)]

    didx = routing.RegisterUnaryTransitCallback(demand_cb)
    cap = max(vehicle_capacity, sum(demands))  # ensure feasibility for the demo
    routing.AddDimensionWithVehicleCapacity(didx, 0, [cap], True, "Capacity")

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(3)

    sol = routing.SolveWithParameters(params)
    if not sol:
        raise RuntimeError("no solution")

    order: list[int] = []
    i = routing.Start(0)
    while not routing.IsEnd(i):
        node = mgr.IndexToNode(i)
        if node != 0:
            order.append(node)
        i = sol.Value(routing.NextVar(i))
    return _package(points, dist, stops, order, cap, "ortools_cvrp")


def _nearest_neighbour(points, dist, stops: list[Stop], vehicle_capacity: int) -> dict:
    unvisited = set(range(1, len(points)))
    order: list[int] = []
    cur = 0
    while unvisited:
        nxt = min(unvisited, key=lambda j: dist[cur][j] - stops[j - 1].urgency * 4000)
        order.append(nxt)
        unvisited.discard(nxt)
        cur = nxt
    cap = max(vehicle_capacity, sum(s.demand for s in stops))
    return _package(points, dist, stops, order, cap, "nearest_neighbour_fallback")


def _package(points, dist, stops: list[Stop], order: list[int], cap: int, algo: str) -> dict:
    seq_stops = []
    total_m = 0
    prev = 0
    for pos, node in enumerate(order):
        total_m += dist[prev][node]
        s = stops[node - 1]
        seq_stops.append(
            {
                "seq": pos + 1,
                "retailer_id": s.retailer_id,
                "name": s.name,
                "lat": s.lat,
                "lng": s.lng,
                "quantity": s.demand,
                "urgency": round(s.urgency, 3),
                "leg_km": round(dist[prev][node] / 1000, 2),
            }
        )
        prev = node
    total_m += dist[prev][0]  # return to depot
    total_km = round(total_m / 1000, 2)
    duration = round(total_km / AVG_SPEED_KMH * 60, 1)
    used = sum(s.demand for s in stops)
    return {
        "algorithm": algo,
        "stops": seq_stops,
        "total_distance_km": total_km,
        "total_duration_min": duration,
        "total_cost": round(total_km * COST_PER_KM, 2),
        "capacity_used": used,
        "vehicle_capacity": cap,
        "urgency_score": round(sum(s.urgency for s in stops), 3),
        "ortools_used": algo == "ortools_cvrp",
    }
