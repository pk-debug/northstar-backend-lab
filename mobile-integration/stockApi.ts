/** Northstar Expo API client; copy to src/features/network/stockApi.ts.
 * WHAT: one mobile API adapter; WHY: swap backend language without changing screens;
 * WHO: Expo Android/iOS/web; WHEN: whenever screens need remote demo state;
 * WHERE: React Native repository; HOW: fetch JSON; HOW MUCH: no SDK fee.
 */
import { Platform } from 'react-native';
import type { MarketAsset, Position, SimulatedOrder, OrderSide } from '../market/types';

/** Set EXPO_PUBLIC_API_URL to your laptop/LAN server before building the app. */
const LOCAL_HOST = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
export const API_URL = process.env.EXPO_PUBLIC_API_URL || LOCAL_HOST;
export type Index = {name:string;value:string;change:string;positive:boolean};
export type Portfolio = {cash:number;positions:Position[];positionsValue:number;totalValue:number};
export type OrderRequest = {symbol:string;side:OrderSide;quantity:number};
export type OrderResult = {ok:true;order:SimulatedOrder}|{ok:false;message:string};

/** Parse success JSON AND human-readable error envelopes consistently. */
async function request<T>(path:string, options?:RequestInit):Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {...options,headers:{'Content-Type':'application/json',...options?.headers}});
  const data = await response.json();
  if (!response.ok) throw new Error(data?.message || `HTTP ${response.status}`);
  return data as T;
}
/** Quotes are sample fixtures, not live prices. */
export const getAssets = (q='') => request<MarketAsset[]>(`/api/v1/assets?q=${encodeURIComponent(q)}`);
export const getAsset = (symbol:string) => request<MarketAsset>(`/api/v1/assets/${encodeURIComponent(symbol)}`);
export const getIndexes = () => request<Index[]>('/api/v1/indexes');
export const getPortfolio = () => request<Portfolio>('/api/v1/portfolio');
export const getOrders = () => request<SimulatedOrder[]>('/api/v1/orders');
/** The idempotency key MUST be stable if a network timeout causes a retry. */
export async function placeOrder(order:OrderRequest, idempotencyKey:string):Promise<OrderResult> {
  return request<OrderResult>('/api/v1/orders',{method:'POST',headers:{'Idempotency-Key':idempotencyKey},body:JSON.stringify(order)});
}
