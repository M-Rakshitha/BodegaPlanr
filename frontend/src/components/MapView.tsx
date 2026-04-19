'use client';
import { useEffect, useRef } from 'react';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

export type MapPin = {
  lat: number;
  lng: number;
  label: string;
  sub?: string;
  active?: boolean;
  draggable?: boolean;
};

type Props = {
  pins: MapPin[];
  center?: [number, number];
  zoom?: number;
  onPinDrag?: (lat: number, lng: number) => void;
};

// Fix Leaflet's broken default icon paths under webpack
const defaultIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

function makeIcon(active: boolean) {
  const color = active ? '#103B58' : '#64748b';
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="44" viewBox="0 0 32 44">
      <path d="M16 0C7.163 0 0 7.163 0 16c0 10.5 16 28 16 28S32 26.5 32 16C32 7.163 24.837 0 16 0z"
        fill="${color}" opacity="0.95"/>
      <circle cx="16" cy="16" r="7" fill="white"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    iconSize: [32, 44],
    iconAnchor: [16, 44],
    popupAnchor: [0, -44],
    className: '',
  });
}

export default function MapView({ pins, center, zoom = 13, onPinDrag }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.Marker[]>([]);

  // Init map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: center ?? [40.7128, -74.006],
      zoom,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
      maxZoom: 19,
    }).addTo(map);

    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // Update pins + fly to new center whenever props change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    pins.forEach((pin) => {
      const marker = L.marker([pin.lat, pin.lng], {
        icon: makeIcon(!!pin.active),
        draggable: !!pin.draggable,
      })
        .addTo(map)
        .bindPopup(
          `<div style="font-family:sans-serif;min-width:140px">
            <p style="font-weight:700;font-size:13px;margin:0 0 2px">${pin.label}</p>
            ${pin.sub ? `<p style="font-size:11px;color:#64748b;margin:0">${pin.sub}</p>` : ''}
            ${pin.draggable ? `<p style="font-size:10px;color:#94a3b8;margin:4px 0 0">Drag to adjust location</p>` : ''}
          </div>`,
          { closeButton: false }
        );

      if (pin.draggable && onPinDrag) {
        marker.on('dragend', () => {
          const { lat, lng } = marker.getLatLng();
          onPinDrag(lat, lng);
        });
        // Show hint popup on first render
        marker.openPopup();
      }

      markersRef.current.push(marker);
    });

    if (center) {
      map.flyTo(center, zoom, { animate: true, duration: 0.8 });
    } else if (pins.length > 0) {
      const group = L.featureGroup(markersRef.current);
      map.fitBounds(group.getBounds().pad(0.3), { animate: true, duration: 0.8 });
    }
  }, [pins, center, zoom]);

  return <div ref={containerRef} className="h-full w-full" />;
}
