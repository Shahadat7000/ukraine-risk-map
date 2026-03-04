import requests
import json
import math
import sys
import folium
import webbrowser
import os
from typing import List, Optional, Tuple, Dict
import concurrent.futures
import random


class UkraineRiskVisualizer:
    """
    Advanced Ukraine Risk Visualization Tool - Competition Grade
    """

    def __init__(self, data_source='city data ukrine.json'):
        # API credentials
        self.api_token = os.getenv("NEWSMATICS_TOKEN")
        self.api_endpoint = "https://api.newsmatics.com/v1"
        self.request_headers = {'Authorization': f'Bearer {self.api_token}', 'Accept': 'application/json'}

        # 1. GEOSPATIAL DATA
        self.russian_controlled_zone = [
            (49.9, 38.5), (49.5, 38.2), (49.0, 38.0), (48.6, 38.0),
            (48.3, 38.0), (48.0, 37.7), (47.7, 37.2), (47.4, 35.8),
            (47.4, 34.6), (46.5, 33.0), (46.5, 31.8), (46.0, 32.0),
            (44.5, 33.0), (44.3, 34.0), (45.3, 36.5), (47.0, 39.0),
            (49.0, 40.0), (49.9, 38.5)
        ]

        # 2. STRATEGIC VALUES
        self.strategic_weights = {
            'Kharkiv': 15, 'Dnipro': 10, 'Zaporizhzhia': 10, 'Kyiv': 5,
            'Odesa': 8, 'Kryvyi Rih': 8, 'Mykolaiv': 5, 'Sloviansk': 12,
            'Kramatorsk': 12, 'Pokrovsk': 15, 'Chasiv Yar': 15
        }

        # 3. COMBAT ZONES
        self.combat_zones = [
            {'label': 'Kupyansk Front', 'position': (49.7, 37.6)},
            {'label': 'Chasiv Yar', 'position': (48.59, 37.85)},
            {'label': 'Pokrovsk Front', 'position': (48.25, 37.20)},
            {'label': 'Vuhledar', 'position': (47.98, 37.30)},
            {'label': 'Robotyne', 'position': (47.45, 35.9)},
            {'label': 'Enerhodar/River', 'position': (47.50, 34.60)},
            {'label': 'Kherson River', 'position': (46.65, 32.70)}
        ]

        # 4. COLORS
        self.risk_colors = {
            'critical': '#c0392b',
            'high': '#e67e22',
            'medium': '#f1c40f',
            'low': '#27ae60',
            'occupied': '#2c3e50'
        }

        self.settlements = self._load_settlement_data(data_source)

    def _load_settlement_data(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self._generate_fallback_data()

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _is_point_in_polygon(self, lat, lon, polygon):
        x, y = lat, lon
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def _fetch_news_parallel(self):
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_city = {
                executor.submit(self._fetch_single_news, city.get('name', 'Unknown')): city.get('name', 'Unknown')
                for city in self.settlements
            }
            for future in concurrent.futures.as_completed(future_to_city):
                city = future_to_city[future]
                try:
                    results[city] = future.result()
                except Exception:
                    results[city] = []
        return results

    def _fetch_single_news(self, settlement: str) -> List:
        query_params = {
            'q': f'"{settlement}" AND (assault OR shelling OR evacuation)',
            'limit': 5,
            'sort': 'date',
            'language': 'en'
        }
        try:
            if "YOUR_TOKEN" in self.api_token: return []  # Offline check

            response = requests.get(
                f"{self.api_endpoint}/search",
                headers=self.request_headers,
                params=query_params,
                timeout=5
            )
            if response.status_code != 200: return []
            payload = response.json()
            return payload.get('articles', []) if isinstance(payload, dict) else []
        except:
            return []

    def _get_field_reports(self, settlement: str) -> Optional[str]:
        intelligence_db = {
            'Kharkiv': "Clashes at Starytsya. Heavy shelling.",
            'Kupyansk': "Clashes at Kruhlyakivka. Enemy assault.",
            'Sloviansk': "Clashes near Yampil.",
            'Kramatorsk': "Active frontline combat near Orikhovo.",
            'Pokrovsk': "Heavy clashes near Rodynske. Critical defense.",
            'Dnipro': "Missile strikes reported.",
            'Zaporizhzhia': "Explosions. Energy infra repairs.",
            'Nikopol': "Artillery shelling across Dnipro.",
            'Kryvyi Rih': "Frequent missile/drone alerts.",
            'Samar': "Strategic proximity to front. Missile threat.",
            'Kamianske': "Industrial hub. Air alert zone."
        }
        return intelligence_db.get(settlement)

    def _compute_advanced_metrics(self, name, min_dist, field_report, news_articles, is_occupied):
        # 1. BASE SCORE
        if min_dist < 15:
            base = 90
        elif min_dist < 40:
            base = 75
        elif min_dist < 80:
            base = 50
        elif min_dist < 150:
            base = 30
        else:
            base = 10

        # 2. STRATEGIC
        strat = self.strategic_weights.get(name, 0)

        # 3. NEWS ANALYSIS
        news_count = len(news_articles)
        news_text = " ".join([a.get('title', '') for a in news_articles]).lower()

        spike_rate = news_count * 2
        if field_report: spike_rate += 3
        spike_rate = min(10, spike_rate)

        momentum = "Stable ➡"
        if "breakthrough" in news_text or "retreat" in news_text:
            momentum = "Surging ⚡"
        elif "evacuation" in news_text or "encirclement" in news_text:
            momentum = "Collapsing 🔻"
        elif "positional" in news_text:
            momentum = "Stalled ⏸"
        elif base > 80:
            momentum = "Active Combat ⚔"

        # 4. FINAL SCORE
        intel_bonus = 0
        if "evacuation" in news_text: intel_bonus += 10
        if "shelling" in news_text: intel_bonus += 5
        if field_report: intel_bonus += 15

        total_score = base + strat + intel_bonus
        if is_occupied: total_score = 100

        risk_score = min(99, max(5, int(total_score)))

        # 5. VOLATILITY
        if spike_rate > 6 and risk_score > 60:
            volatility = "High 🔴"
        elif spike_rate > 3 or risk_score > 40:
            volatility = "Medium 🟠"
        else:
            volatility = "Low 🟢"

        # 6. TIMELINE
        if risk_score > 85:
            timeline = "CRITICAL: < 48 Hours"
        elif risk_score > 60:
            timeline = "High Risk: < 7 Days"
        elif risk_score > 30:
            timeline = "Contested: > 7 Days"
        else:
            timeline = "Safe from Ground Assault"

        if is_occupied:
            timeline = "Occupied"
            volatility = "Static"
            momentum = "Entrenched"

        return {
            "score": risk_score,
            "probability": risk_score,
            "momentum": momentum,
            "volatility": volatility,
            "spike_rate": spike_rate,
            "timeline": timeline
        }

    def _evaluate_settlement(self, settlement, news_cache):
        name = settlement.get('name', 'Unknown')
        lat = settlement.get('coordinates', {}).get('lat', 0)
        lon = settlement.get('coordinates', {}).get('lon', 0)

        # Geometric Check
        is_occupied_geo = self._is_point_in_polygon(lat, lon, self.russian_controlled_zone)

        # --- FIX: ADDED DOVZHANSK AND OTHERS TO MANUAL LIST ---
        manual_occupied_list = [
            "Donetsk", "Luhansk", "Mariupol", "Melitopol", "Berdiansk", "Kerch",
            "Simferopol", "Sevastopol", "Yalta", "Lysychansk", "Sievierodonetsk",
            "Bakhmut", "Avdiivka", "Dovzhansk", "Khartsyzk", "Khrustalnyi",
            "Yenakiieve", "Kadiivka", "Alchevsk", "Horlivka", "Makiivka"
        ]

        is_occupied = is_occupied_geo or (name in manual_occupied_list)

        min_dist = 1000
        for zone in self.combat_zones:
            d = self._haversine_distance(lat, lon, zone['position'][0], zone['position'][1])
            if d < min_dist: min_dist = d

        field_report = self._get_field_reports(name)
        news_data = news_cache.get(name, [])

        metrics = self._compute_advanced_metrics(name, min_dist, field_report, news_data, is_occupied)

        if is_occupied:
            cat = "OCCUPIED"
            hue = self.risk_colors['occupied']
            size, glow = 6, False
        elif metrics['score'] >= 85:
            cat = "CRITICAL"
            hue = self.risk_colors['critical']
            size, glow = 10, True
        elif metrics['score'] >= 60:
            cat = "HIGH"
            hue = self.risk_colors['high']
            size, glow = 8, False
        elif metrics['score'] >= 30:
            cat = "MEDIUM"
            hue = self.risk_colors['medium']
            size, glow = 7, False
        else:
            cat = "LOW"
            hue = self.risk_colors['low']
            size, glow = 6, False

        range_text = f"{int(min_dist)} km"

        info_panel = self._build_info_panel(
            name, cat, metrics['probability'], metrics['timeline'],
            range_text, field_report or "Monitoring",
            metrics['momentum'], metrics['volatility'], metrics['spike_rate']
        )

        return {
            'name': name, 'lat': lat, 'lon': lon,
            'condition': cat, 'marker_hue': hue, 'marker_size': size,
            'glow_effect': glow, 'info_panel': info_panel
        }

    def _build_info_panel(self, name, level, capture, timeline, distance, intel, momentum, volatility, spike_rate):
        colors = {
            "CRITICAL": "#c0392b", "HIGH": "#e67e22",
            "MEDIUM": "#f1c40f", "LOW": "#27ae60", "OCCUPIED": "#2c3e50"
        }
        header_color = colors.get(level, "#333")
        prob_color = "red" if capture > 50 else "orange" if capture > 20 else "green"

        spike_visual = "<span style='color:red;'>" + ("|" * spike_rate) + "</span>" + (
                    "<span style='color:#ccc;'>" + ("|" * (10 - spike_rate)) + "</span>")

        if level == "OCCUPIED":
            return f"""
            <div style="font-family: Arial, sans-serif; width: 300px; font-size: 12px;">
                <h3 style="margin:0 0 8px 0; border-bottom: 3px solid #2c3e50; color:#2c3e50; text-transform:uppercase;">
                    {name}
                </h3>
                <div style="background-color:#f0f0f0; padding:5px; margin-bottom:5px; border-radius:4px;">
                    <b>Risk Score:</b> 
                    <span style="color:#2c3e50; font-size:14px; font-weight:bold; float:right;">100% (OCCUPIED)</span>
                </div>
                <div style="font-style:italic; color:#555; border-left: 2px solid #999; padding-left: 5px;">
                    "Territory under Russian control"
                </div>
            </div>
            """

        return f"""
        <div style="font-family: Arial, sans-serif; width: 300px; font-size: 12px;">
            <h3 style="margin:0 0 8px 0; border-bottom: 3px solid {header_color}; color:{header_color}; text-transform:uppercase;">
                {name}
            </h3>
            <div style="background-color:#f0f0f0; padding:5px; margin-bottom:5px; border-radius:4px;">
                <b>Risk Score:</b> 
                <span style="color:{prob_color}; font-size:14px; font-weight:bold; float:right;">{capture}% ({level})</span>
            </div>
            <table style="width:100%; border-collapse: collapse; margin-bottom: 8px;">
                <tr><td style="color:#555;">Momentum:</td><td style="font-weight:bold;">{momentum}</td></tr>
                <tr><td style="color:#555;">Volatility:</td><td>{volatility}</td></tr>
                <tr><td style="color:#555;">Intel Spike:</td><td>{spike_visual}</td></tr>
            </table>
            <div style="font-style:italic; color:#555; border-left: 2px solid #999; padding-left: 5px;">
                "{intel}"
            </div>
            <div style="font-size:10px; color:#777; margin-top:5px; text-align:right;">
                Range: {distance} | Timeline: {timeline}
            </div>
        </div>
        """

    def render_visualization(self, output_filename='ukraine_risk_map.html'):
        print("🚀 Initializing Advanced Risk Engine...")
        print("📡 Fetching intelligence data streams (Parallel)...")
        news_cache = self._fetch_news_parallel()

        map_canvas = folium.Map(location=[48.3, 36.0], zoom_start=6, tiles='CartoDB positron')

        folium.Polygon(
            locations=self.russian_controlled_zone,
            color="#c0392b", weight=2, fill=True, fill_color="#e74c3c", fill_opacity=0.2,
            popup="Russian Occupied Territory"
        ).add_to(map_canvas)

        total = len(self.settlements)
        for idx, settlement in enumerate(self.settlements):
            pct = int(((idx + 1) / total) * 100)
            sys.stdout.write(
                f'\r[{"█" * int(pct / 4)}{"-" * (25 - int(pct / 4))}] {pct}% | Analyzing: {settlement["name"]:<15}')
            sys.stdout.flush()

            analysis = self._evaluate_settlement(settlement, news_cache)

            if analysis.get('glow_effect'):
                folium.CircleMarker(
                    location=[analysis['lat'], analysis['lon']],
                    radius=30, color=analysis['marker_hue'], fill=True, fill_opacity=0.2, weight=0
                ).add_to(map_canvas)

            folium.CircleMarker(
                location=[analysis['lat'], analysis['lon']],
                radius=analysis['marker_size'],
                color="white", weight=1,
                fill=True, fill_color=analysis['marker_hue'], fill_opacity=1.0,
                popup=folium.Popup(analysis['info_panel'], max_width=320),
                tooltip=f"{analysis['name']} ({analysis['condition']})"
            ).add_to(map_canvas)

        print("\n\n✅ Visualization Complete.")

        legend_panel = '''
        <div style="position: fixed; bottom: 30px; left: 30px; width: 180px; 
                    background:white; padding: 10px; border: 1px solid #ccc; border-radius:5px; z-index:9999; font-size:11px; font-family:Arial;">
            <b>Risk Prediction Model</b><br>
            <span style="color:#c0392b;">●</span> Critical (90-100%)<br>
            <span style="color:#e67e22;">●</span> High Risk (60-89%)<br>
            <span style="color:#f1c40f;">●</span> Medium Alert (30-59%)<br>
            <span style="color:#27ae60;">●</span> Low Risk (0-29%)<br>
            <span style="color:#2c3e50;">●</span> Occupied City (100%)<br>
            <span style="background:#e74c3c; opacity:0.4; padding:0 5px;">&nbsp;&nbsp;&nbsp;</span> Occupied Zone
        </div>
        '''
        map_canvas.get_root().html.add_child(folium.Element(legend_panel))
        map_canvas.save(output_filename)
        print(f"🗺️ Map created: {output_filename}")
        try:
            webbrowser.open('file://' + os.path.realpath(output_filename))
        except:
            pass

    def _generate_fallback_data(self):
        """Standard fallback data for offline mode"""
        return [
            {"name": "Kharkiv", "coordinates": {"lat": 50.0044, "lon": 36.2313}},
            {"name": "Sloviansk", "coordinates": {"lat": 48.8700, "lon": 37.6250}},
            {"name": "Kostiantynivka", "coordinates": {"lat": 48.5333, "lon": 37.7166}},
            {"name": "Dnipro", "coordinates": {"lat": 48.45, "lon": 34.9833}},
            {"name": "Zaporizhzhia", "coordinates": {"lat": 47.8377, "lon": 35.1383}},
            {"name": "Kryvyi Rih", "coordinates": {"lat": 47.91, "lon": 33.3916}},
            {"name": "Kherson", "coordinates": {"lat": 46.6333, "lon": 32.6}},
            {"name": "Sumy", "coordinates": {"lat": 50.9166, "lon": 34.75}},
            {"name": "Kamianske", "coordinates": {"lat": 48.5166, "lon": 34.6166}},
            {"name": "Nikopol", "coordinates": {"lat": 47.5666, "lon": 34.4}},
            {"name": "Kramatorsk", "coordinates": {"lat": 48.7391, "lon": 37.5841}},
            {"name": "Pokrovsk", "coordinates": {"lat": 48.2833, "lon": 37.1833}},
            {"name": "Chasiv Yar", "coordinates": {"lat": 48.59, "lon": 37.85}},
            {"name": "Mykolaiv", "coordinates": {"lat": 46.9666, "lon": 32.0}},
            {"name": "Pavlohrad", "coordinates": {"lat": 48.5166, "lon": 35.8666}},
            {"name": "Kyiv", "coordinates": {"lat": 50.45, "lon": 30.5233}},
            {"name": "Odesa", "coordinates": {"lat": 46.4857, "lon": 30.7434}},
            {"name": "Lviv", "coordinates": {"lat": 49.8419, "lon": 24.0316}},
            {"name": "Vinnytsia", "coordinates": {"lat": 49.2333, "lon": 28.4833}},
            {"name": "Donetsk", "coordinates": {"lat": 48.0088, "lon": 37.8041}},
            {"name": "Luhansk", "coordinates": {"lat": 48.57, "lon": 39.33}},
            {"name": "Mariupol", "coordinates": {"lat": 47.0958, "lon": 37.5494}},
            {"name": "Simferopol", "coordinates": {"lat": 44.9483, "lon": 34.1000}},
            {"name": "Dovzhansk", "coordinates": {"lat": 48.0833, "lon": 39.65}},
            {"name": "Khartsyzk", "coordinates": {"lat": 48.0333, "lon": 38.15}}
        ]


if __name__ == "__main__":
    visualizer = UkraineRiskVisualizer()

    visualizer.render_visualization('ukraine_risk_map.html')
