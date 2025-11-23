#!/usr/bin/env python3
"""
SPY Trading Suite v4.3 - TradingView Price Edition
- Gets price from TradingView chart (no IBKR data subscription needed)
- IBKR only used for order execution
- All calculations based on TV chart price
"""
import json, threading, queue, re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from ib_insync import IB, Option, LimitOrder, Stock, util
import socket, sys
import asyncio

VERSION = "4.3.0"

HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SPY Trading Suite v4.3</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: system-ui, -apple-system; }
        
        .mid-highlight { 
            background: linear-gradient(to right, rgba(34, 197, 94, 0.5), rgba(34, 197, 94, 0.2)); 
            border: 3px solid rgb(34, 197, 94) !important;
            box-shadow: 0 0 20px rgba(34, 197, 94, 0.6), inset 0 0 10px rgba(34, 197, 94, 0.3);
            font-size: 1.1rem;
            font-weight: 900;
            position: relative;
        }
        
        .mid-highlight::before {
            content: 'MID PRICE';
            position: absolute;
            left: -90px;
            top: 50%;
            transform: translateY(-50%);
            color: rgb(34, 197, 94);
            font-size: 0.7rem;
            font-weight: bold;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .ladder-scroll { 
            max-height: 500px; 
            overflow-y: auto;
            position: relative;
        }
        
        .selected-row {
            background: linear-gradient(to right, rgba(59, 130, 246, 0.5), rgba(59, 130, 246, 0.2));
            border: 2px solid rgb(59, 130, 246) !important;
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
        }
        
        .ladder-row {
            transition: all 0.2s ease;
        }
        
        .ladder-row:hover {
            transform: translateX(5px);
        }
        
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        
        .status-connected { background: #22c55e; box-shadow: 0 0 10px #22c55e; }
        .status-disconnected { background: #ef4444; box-shadow: 0 0 10px #ef4444; }
        
        .btn-place {
            background: linear-gradient(135deg, #22c55e, #16a34a);
            box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
        }
        
        .btn-cancel {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4);
        }
        
        .btn-close {
            background: linear-gradient(135deg, #f97316, #ea580c);
            box-shadow: 0 4px 15px rgba(249, 115, 22, 0.4);
        }
        
        .chart-container {
            position: relative;
        }
        
        .trade-lines-overlay {
            position: absolute;
            top: 60px;
            left: 20px;
            background: rgba(0, 0, 0, 0.8);
            border: 1px solid rgba(6, 182, 212, 0.5);
            border-radius: 8px;
            padding: 12px;
            z-index: 1000;
            min-width: 200px;
        }
        
        .line-indicator {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 8px;
            margin: 4px 0;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        
        .line-entry {
            background: rgba(6, 182, 212, 0.2);
            border-left: 3px solid #06b6d4;
        }
        
        .line-tp {
            background: rgba(34, 197, 94, 0.2);
            border-left: 3px solid #22c55e;
        }
        
        .line-sl {
            background: rgba(239, 68, 68, 0.2);
            border-left: 3px solid #ef4444;
        }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950 text-white">
    <div class="border-b border-blue-900/50 bg-black/40 px-6 py-3 sticky top-0 z-50">
        <div class="flex justify-between items-center">
            <div class="flex items-center gap-3">
                <div id="status-dot" class="status-dot status-disconnected"></div>
                <h1 class="text-2xl font-bold text-cyan-400">SPY Trading Suite v4.3</h1>
                <span class="text-xs text-gray-400 bg-blue-900/30 px-2 py-1 rounded">TV PRICE</span>
            </div>
            <div class="text-right flex items-center gap-4">
                <div class="flex gap-2">
                    <input id="manual-price-input" type="number" step="0.01" placeholder="Enter price" 
                           class="bg-black/40 border border-cyan-600 text-cyan-400 px-3 py-2 rounded text-lg font-bold w-32 text-center"
                           onchange="updateManualPrice()">
                    <button onclick="fetchCurrentPrice()" class="bg-gradient-to-r from-green-600 to-green-500 hover:from-green-500 hover:to-green-400 text-white px-4 py-2 rounded font-bold text-sm">
                        FETCH
                    </button>
                    <div class="text-xs text-gray-400 self-end mb-2">Manual Price</div>
                </div>
                <div>
                    <div id="spy-live" class="text-4xl font-bold text-cyan-400">$---</div>
                    <div class="text-xs text-gray-400">CURRENT PRICE</div>
                </div>
            </div>
        </div>
    </div>

    <div class="border-b border-blue-900/50 bg-black/20 px-6 flex gap-1">
        <button onclick="switchTab('dashboard')" id="tab-dashboard" class="px-6 py-3 border-b-2 border-cyan-400 text-cyan-400 font-bold">DASHBOARD</button>
        <button onclick="switchTab('trades')" id="tab-trades" class="px-6 py-3 border-b-2 border-transparent text-gray-400 hover:text-cyan-300">TRADES</button>
        <button onclick="switchTab('settings')" id="tab-settings" class="px-6 py-3 border-b-2 border-transparent text-gray-400 hover:text-cyan-300">SETTINGS</button>
    </div>

    <div class="flex h-screen overflow-hidden">
        <div class="flex-1 overflow-y-auto bg-blue-900/10">
            <div id="dashboard" class="p-4 h-full">
                <div class="bg-blue-900/20 rounded-xl border border-blue-800 h-full flex flex-col">
                    <div class="p-4 border-b border-blue-800">
                        <h2 class="text-lg font-bold text-cyan-400">TradingView SPY Chart</h2>
                        <p class="text-xs text-gray-400 mt-1">Price source for all calculations</p>
                    </div>
                    <div class="flex-1 overflow-hidden chart-container">
                        <div id="tradingview_chart" style="height: 100%"></div>
                        <div class="trade-lines-overlay" id="trade-lines">
                            <div class="text-xs text-gray-400 mb-2 font-bold">TRADE LEVELS</div>
                            <div class="line-entry line-indicator">
                                <span class="text-xs text-gray-300">ENTRY</span>
                                <span class="font-bold text-cyan-300" id="overlay-entry">$---</span>
                            </div>
                            <div class="line-tp line-indicator">
                                <span class="text-xs text-gray-300">TP</span>
                                <span class="font-bold text-green-300" id="overlay-tp">$---</span>
                            </div>
                            <div class="line-sl line-indicator">
                                <span class="text-xs text-gray-300">SL</span>
                                <span class="font-bold text-red-300" id="overlay-sl">$---</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="trades" class="hidden p-4">
                <h2 class="text-2xl font-bold text-cyan-400 mb-4">Trade History</h2>
                <div id="trades-list" class="space-y-2"></div>
            </div>

            <div id="settings" class="hidden p-4 overflow-y-auto">
                <h2 class="text-2xl font-bold text-cyan-400 mb-4">Configuration</h2>
                <div class="grid grid-cols-2 gap-6 max-w-4xl">
                    <div class="bg-blue-900/20 rounded-xl p-6 border border-blue-800 space-y-4">
                        <h3 class="text-lg font-bold text-cyan-400">IBKR Connection</h3>
                        <p class="text-xs text-gray-400">Only for order execution, not data</p>
                        <div>
                            <label class="text-xs text-gray-400">Host</label>
                            <input id="ibkr-host" type="text" value="127.0.0.1" class="w-full bg-black/40 border border-blue-700 text-white px-3 py-2 rounded text-sm">
                        </div>
                        <div>
                            <label class="text-xs text-gray-400">Port (7497=Paper, 7496=Live)</label>
                            <input id="ibkr-port" type="number" value="7497" class="w-full bg-black/40 border border-blue-700 text-white px-3 py-2 rounded text-sm">
                        </div>
                        <div>
                            <label class="text-xs text-gray-400">Client ID</label>
                            <input id="ibkr-cid" type="number" value="1" class="w-full bg-black/40 border border-blue-700 text-white px-3 py-2 rounded text-sm">
                        </div>
                        <button onclick="testIBKR()" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded text-sm">TEST CONNECTION</button>
                        <div id="ibkr-status" class="text-sm text-red-400">Not Connected</div>
                    </div>

                    <div class="bg-blue-900/20 rounded-xl p-6 border border-blue-800 space-y-4">
                        <h3 class="text-lg font-bold text-cyan-400">Trade Defaults</h3>
                        <div>
                            <label class="text-xs text-gray-400">Default TP ($)</label>
                            <input id="default-tp" type="number" value="0.05" step="0.01" class="w-full bg-black/40 border border-blue-700 text-white px-3 py-2 rounded text-sm">
                        </div>
                        <div>
                            <label class="text-xs text-gray-400">Default SL ($)</label>
                            <input id="default-sl" type="number" value="0.03" step="0.01" class="w-full bg-black/40 border border-blue-700 text-white px-3 py-2 rounded text-sm">
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="w-2/5 bg-slate-900/50 border-l border-blue-800 overflow-y-auto flex flex-col">
            <div class="border-b border-blue-800 p-4 bg-blue-900/10">
                <h2 class="text-lg font-bold text-cyan-400 mb-3">Strike Selection</h2>
                <div class="space-y-2 text-sm">
                    <div>
                        <label class="text-xs text-gray-400">Strike Price</label>
                        <input id="strike-input" type="number" step="1" placeholder="e.g. 600" class="w-full bg-black/40 border border-blue-700 text-white px-2 py-1 rounded text-xs">
                    </div>
                    <div>
                        <label class="text-xs text-gray-400">Expiration (YYYYMMDD)</label>
                        <input id="expiry-input" type="text" placeholder="e.g. 20250124" class="w-full bg-black/40 border border-blue-700 text-white px-2 py-1 rounded text-xs">
                    </div>
                    <div>
                        <label class="text-xs text-gray-400">Option Type</label>
                        <select id="option-type" class="w-full bg-black/40 border border-blue-700 text-white px-2 py-1 rounded text-xs">
                            <option value="C">CALL</option>
                            <option value="P">PUT</option>
                        </select>
                    </div>
                    <button onclick="setStrike()" class="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white font-bold py-2 rounded text-sm mt-2">SET STRIKE</button>
                    
                    <div id="strike-info" class="text-xs bg-gradient-to-r from-green-900/40 to-transparent p-3 rounded border border-green-700 hidden mt-2">
                        <div class="flex justify-between mb-1">
                            <span class="text-gray-400">Strike:</span>
                            <span class="text-green-300 font-bold text-base" id="selected-strike">---</span>
                        </div>
                        <div class="flex justify-between mb-1">
                            <span class="text-gray-400">Expiry:</span>
                            <span class="text-cyan-300 font-bold" id="selected-expiry">---</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-400">Type:</span>
                            <span class="text-cyan-300 font-bold" id="selected-type">---</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="border-b border-blue-800 p-4 bg-gradient-to-r from-blue-900/20 to-transparent">
                <h3 class="text-sm font-bold text-cyan-400 mb-2">Current Trade Levels</h3>
                <div class="space-y-2">
                    <div class="flex justify-between items-center bg-blue-600/20 p-2 rounded border border-blue-600">
                        <span class="text-xs text-gray-400">Entry (SPY):</span>
                        <span class="text-cyan-300 font-bold text-lg" id="chart-trigger">$---</span>
                    </div>
                    <div class="flex justify-between items-center bg-green-600/20 p-2 rounded border border-green-600">
                        <span class="text-xs text-gray-400">TP Target:</span>
                        <span class="text-green-300 font-bold text-lg" id="chart-tp">$---</span>
                    </div>
                    <div class="flex justify-between items-center bg-red-600/20 p-2 rounded border border-red-600">
                        <span class="text-xs text-gray-400">SL Stop:</span>
                        <span class="text-red-300 font-bold text-lg" id="chart-sl">$---</span>
                    </div>
                </div>
            </div>

            <div class="border-b border-blue-800 p-4 flex-1 flex flex-col">
                <div class="flex justify-between items-center mb-2">
                    <h2 class="text-lg font-bold text-cyan-400">Option Price Ladder</h2>
                    <div class="text-xs text-gray-400">
                        <span>Mid: <span id="ladder-mid" class="text-green-300 font-bold text-base">$2.50</span></span>
                    </div>
                </div>
                
                <div class="flex gap-2 mb-3">
                    <button onclick="ladderUp()" class="flex-1 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white py-2 rounded font-bold text-sm">UP</button>
                    <button onclick="centerLadder()" class="flex-1 bg-gradient-to-r from-green-600 to-green-500 hover:from-green-500 hover:to-green-400 text-white py-2 rounded font-bold text-sm">MID</button>
                    <button onclick="ladderDown()" class="flex-1 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white py-2 rounded font-bold text-sm">DOWN</button>
                </div>
                
                <div id="ladder-display" class="ladder-scroll space-y-1"></div>
            </div>

            <div class="border-t border-blue-800 p-4 space-y-3 bg-slate-900">
                <div class="bg-blue-900/30 p-3 rounded border border-blue-700">
                    <label class="text-xs text-gray-400">Selected Option Price</label>
                    <div id="quick-price" class="text-3xl font-bold text-green-400">$2.50</div>
                </div>
                
                <div class="bg-blue-900/30 p-3 rounded border border-blue-700">
                    <label class="text-xs text-gray-400">Entry Trigger (SPY Price)</label>
                    <div id="quick-trigger" class="text-3xl font-bold text-cyan-400">$---</div>
                </div>
                
                <div class="grid grid-cols-3 gap-2 text-xs">
                    <div>
                        <label class="text-gray-400 block mb-1">TP ($)</label>
                        <input id="tp-input" type="number" value="0.05" step="0.01" class="w-full bg-black/40 border border-green-700 text-white px-2 py-2 rounded text-sm font-bold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1">SL ($)</label>
                        <input id="sl-input" type="number" value="0.03" step="0.01" class="w-full bg-black/40 border border-red-700 text-white px-2 py-2 rounded text-sm font-bold">
                    </div>
                    <div>
                        <label class="text-gray-400 block mb-1">Qty</label>
                        <input id="qty-input" type="number" value="1" min="1" class="w-full bg-black/40 border border-blue-700 text-white px-2 py-2 rounded text-sm font-bold">
                    </div>
                </div>
                
                <button onclick="quickExecute()" class="w-full btn-place text-white font-bold py-4 rounded text-base hover:scale-[1.02] transition-transform">
                    PLACE ORDER
                </button>
                <button onclick="cancelOrder()" class="w-full btn-cancel text-white font-bold py-3 rounded text-sm hover:scale-[1.02] transition-transform">
                    CANCEL ORDER
                </button>
                <button onclick="closePosition()" class="w-full btn-close text-white font-bold py-3 rounded text-sm hover:scale-[1.02] transition-transform">
                    CLOSE POSITION
                </button>
            </div>
        </div>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    
    <script>
        let spyPrice = null;
        let lastSpyPrice = null;
        let selectedLadderIndex = 0;
        let currentStrike = null;
        let currentExpiry = null;
        let currentType = 'C';
        let currentOptionPrice = 2.50;
        let activeOrderId = null;
        let activeTradeId = null;
        let chartWidget = null;
        let priceCheckInterval = null;

        let optionPrices = [];
        for (let i = 0; i <= 1000; i++) {
            optionPrices.push((i * 0.01).toFixed(2));
        }

        function initChart() {
            chartWidget = new TradingView.widget({
                "autosize": true,
                "symbol": "NASDAQ:SPY",
                "interval": "1",
                "timezone": "America/New_York",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": false,
                "container_id": "tradingview_chart"
            });
            
            setTimeout(startPriceExtraction, 2000);
        }

        function updateManualPrice() {
            let manualInput = document.getElementById('manual-price-input').value;
            if (manualInput && manualInput.length > 0) {
                lastSpyPrice = spyPrice;
                spyPrice = parseFloat(manualInput);
                updatePriceDisplay();
                console.log('Manual price set: $' + spyPrice.toFixed(2));
            }
        }

        function fetchCurrentPrice() {
            let manualInput = document.getElementById('manual-price-input').value;
            if (manualInput && manualInput.length > 0) {
                updateManualPrice();
            } else {
                extractPriceFromChart();
                if (spyPrice) {
                    alert('Price fetched: $' + spyPrice.toFixed(2));
                } else {
                    alert('Could not extract price from chart. Please enter manually.');
                }
            }
        }

        function startPriceExtraction() {
            priceCheckInterval = setInterval(extractPriceFromChart, 500);
        }

        function extractPriceFromChart() {
            try {
                let manualInput = document.getElementById('manual-price-input').value;
                if (manualInput && manualInput.length > 0) {
                    return;
                }
                
                let priceFound = false;
                
                let allText = document.body.innerText || document.body.textContent;
                let pricePattern = /149\.\d{2}/g;
                let matches = allText.match(pricePattern);
                
                if (matches && matches.length > 0) {
                    let price = parseFloat(matches[0]);
                    if (price > 140 && price < 160) {
                        lastSpyPrice = spyPrice;
                        spyPrice = price;
                        priceFound = true;
                        updatePriceDisplay();
                        return;
                    }
                }
                
                let ohlcPattern = /O\s*(\d+\.\d{2})\s*H\s*(\d+\.\d{2})\s*L\s*(\d+\.\d{2})\s*C\s*(\d+\.\d{2})/;
                let ohlcMatch = allText.match(ohlcPattern);
                
                if (ohlcMatch) {
                    let closePrice = parseFloat(ohlcMatch[4]);
                    if (closePrice > 140 && closePrice < 160) {
                        lastSpyPrice = spyPrice;
                        spyPrice = closePrice;
                        priceFound = true;
                        updatePriceDisplay();
                        return;
                    }
                }
                
                let generalPattern = /(\d{3}\.\d{2})/g;
                let allMatches = allText.match(generalPattern);
                
                if (allMatches) {
                    for (let match of allMatches) {
                        let price = parseFloat(match);
                        if (price > 140 && price < 160) {
                            lastSpyPrice = spyPrice;
                            spyPrice = price;
                            priceFound = true;
                            updatePriceDisplay();
                            return;
                        }
                    }
                }
                
            } catch (e) {
                console.error('Price extraction error:', e);
            }
        }

        function updatePriceDisplay() {
            if (spyPrice === null) return;
            
            document.getElementById('spy-live').innerText = '$' + spyPrice.toFixed(2);
            
            if (lastSpyPrice === null || Math.abs(spyPrice - lastSpyPrice) > 0.01) {
                renderLadder();
            }
            
            fetch('/api/update_price', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({price: spyPrice})
            }).catch(e => {});
        }

        function updateTradeLevels() {
            if (spyPrice === null) return;
            
            let triggerPrice = spyPrice + (selectedLadderIndex * 0.01);
            let tpPrice = triggerPrice + parseFloat(document.getElementById('tp-input').value);
            let slPrice = triggerPrice - parseFloat(document.getElementById('sl-input').value);
            
            document.getElementById('chart-trigger').innerText = '$' + triggerPrice.toFixed(2);
            document.getElementById('chart-tp').innerText = '$' + tpPrice.toFixed(2);
            document.getElementById('chart-sl').innerText = '$' + slPrice.toFixed(2);
            
            document.getElementById('overlay-entry').innerText = '$' + triggerPrice.toFixed(2);
            document.getElementById('overlay-tp').innerText = '$' + tpPrice.toFixed(2);
            document.getElementById('overlay-sl').innerText = '$' + slPrice.toFixed(2);
        }

        function renderLadder() {
            if (spyPrice === null) {
                document.getElementById('ladder-display').innerHTML = '<p class="text-center text-gray-400 py-4">Waiting for chart price...</p>';
                return;
            }
            
            let midIdx = 250;
            let selectedIdx = midIdx + selectedLadderIndex;
            let selectedTriggerPrice = spyPrice + (selectedLadderIndex * 0.01);

            let start = Math.max(0, selectedIdx - 15);
            let end = Math.min(optionPrices.length, selectedIdx + 16);
            let display = optionPrices.slice(start, end);

            let html = display.map((optPrice, i) => {
                let actualIdx = start + i;
                let offset = (actualIdx - midIdx) * 0.01;
                let triggerPrice = spyPrice + offset;
                let isSelected = actualIdx === selectedIdx;
                let isMid = Math.abs(triggerPrice - spyPrice) < 0.005;

                let cssClass = 'ladder-row w-full p-3 rounded text-sm font-mono transition-all ';
                
                if (isMid) {
                    cssClass += 'mid-highlight text-white';
                } else if (isSelected) {
                    cssClass += 'selected-row text-white font-bold';
                } else {
                    cssClass += 'bg-gray-800/50 text-gray-200 hover:bg-gray-700/70 border border-gray-700';
                }

                return '<button onclick="selectLadder(' + actualIdx + ')" class="' + cssClass + '"><div class="flex justify-between items-center"><span class="text-base font-bold">$' + optPrice + '</span><span class="text-sm text-gray-400">-></span><span class="text-base font-bold">$' + triggerPrice.toFixed(2) + '</span></div></button>';
            }).join('');

            document.getElementById('ladder-display').innerHTML = html;

            currentOptionPrice = parseFloat(optionPrices[selectedIdx]);
            document.getElementById('quick-price').innerText = '$' + optionPrices[selectedIdx];
            document.getElementById('quick-trigger').innerText = '$' + selectedTriggerPrice.toFixed(2);
            document.getElementById('ladder-mid').innerText = '$' + optionPrices[midIdx];
            
            updateTradeLevels();
        }

        function selectLadder(idx) {
            selectedLadderIndex = idx - 250;
            renderLadder();
        }

        function ladderUp() {
            if (selectedLadderIndex < 250) selectedLadderIndex++;
            renderLadder();
        }

        function ladderDown() {
            if (selectedLadderIndex > -250) selectedLadderIndex--;
            renderLadder();
        }

        function centerLadder() {
            selectedLadderIndex = 0;
            renderLadder();
        }

        function setStrike() {
            let strike = parseFloat(document.getElementById('strike-input').value);
            let expiry = document.getElementById('expiry-input').value;
            let type = document.getElementById('option-type').value;
            
            if (!strike || !expiry) {
                alert('Please enter strike price and expiration date');
                return;
            }
            
            currentStrike = strike;
            currentExpiry = expiry;
            currentType = type;
            
            document.getElementById('selected-strike').innerText = '$' + strike.toFixed(2);
            document.getElementById('selected-expiry').innerText = expiry;
            document.getElementById('selected-type').innerText = type === 'C' ? 'CALL' : 'PUT';
            document.getElementById('strike-info').classList.remove('hidden');
            
            alert('Strike set: $' + strike.toFixed(2) + ' ' + expiry + ' ' + (type === 'C' ? 'CALL' : 'PUT'));
        }

        async function quickExecute() {
            if (!currentStrike || !currentExpiry) {
                alert('Please set strike first!');
                return;
            }

            if (spyPrice === null) {
                alert('Waiting for price data...');
                return;
            }

            let optionPrice = currentOptionPrice;
            let triggerPrice = spyPrice + (selectedLadderIndex * 0.01);
            let tp = parseFloat(document.getElementById('tp-input').value);
            let sl = parseFloat(document.getElementById('sl-input').value);
            let qty = parseInt(document.getElementById('qty-input').value);

            try {
                let res = await fetch('/api/execute_trade', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        price: optionPrice,
                        strike: currentStrike,
                        expiry: currentExpiry,
                        type: currentType,
                        qty: qty,
                        tp: tp,
                        sl: sl,
                        trigger_price: triggerPrice
                    })
                });
                
                let data = await res.json();
                
                if (data.status === 'success') {
                    activeOrderId = data.order_id;
                    activeTradeId = data.order_id;
                    alert('Order Placed: ' + qty + 'x @ $' + optionPrice.toFixed(2) + ' Entry $' + triggerPrice.toFixed(2) + ' (Order #' + data.order_id + ')');
                    addTradeToList(optionPrice, triggerPrice, tp, sl, qty, 'PENDING', data.order_id);
                } else {
                    alert('Error: ' + data.message);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function cancelOrder() {
            if (!activeOrderId) {
                alert('No active order to cancel');
                return;
            }

            try {
                let res = await fetch('/api/cancel_order', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({order_id: activeOrderId})
                });
                
                let data = await res.json();
                
                if (data.status === 'success') {
                    activeOrderId = null;
                    alert('Order cancelled');
                } else {
                    alert('Error: ' + data.message);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function closePosition() {
            if (!activeTradeId) {
                alert('No active position to close');
                return;
            }

            try {
                let res = await fetch('/api/close_position', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({trade_id: activeTradeId})
                });
                
                let data = await res.json();
                
                if (data.status === 'success') {
                    activeTradeId = null;
                    alert('Position closed');
                } else {
                    alert('Error: ' + data.message);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function cancelOrderById(orderId) {
            if (!confirm('Cancel Order #' + orderId + '?')) {
                return;
            }

            try {
                let res = await fetch('/api/cancel_order', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({order_id: orderId})
                });
                
                let data = await res.json();
                
                if (data.status === 'success') {
                    alert('Order #' + orderId + ' cancelled successfully');
                    // Refresh the page or update the UI
                    location.reload();
                } else {
                    alert('Error cancelling order: ' + data.message);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        async function closePositionById(tradeId) {
            if (!confirm('Close Position #' + tradeId + '?')) {
                return;
            }

            try {
                let res = await fetch('/api/close_position', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({trade_id: tradeId})
                });
                
                let data = await res.json();
                
                if (data.status === 'success') {
                    alert('Position #' + tradeId + ' closed successfully');
                    // Refresh the page or update the UI
                    location.reload();
                } else {
                    alert('Error closing position: ' + data.message);
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function addTradeToList(price, trigger, tp, sl, qty, status, orderId) {
            let list = document.getElementById('trades-list');
            let now = new Date().toLocaleTimeString();
            
            let statusColor = status === 'PENDING' ? 'cyan' : 
                            status === 'FILLED' ? 'green' : 
                            status === 'CANCELLED' ? 'red' : 'gray';
            
            // Add action buttons based on status
            let actionButtons = '';
            if (status === 'PENDING' && orderId) {
                actionButtons = `
                    <div class="mt-3 flex gap-2">
                        <button onclick="cancelOrderById(${orderId})" 
                                class="flex-1 bg-gradient-to-r from-red-600 to-red-500 hover:from-red-500 hover:to-red-400 text-white font-bold py-2 px-3 rounded text-xs transition-all">
                            CANCEL ORDER
                        </button>
                    </div>
                `;
            } else if (status === 'FILLED' && orderId) {
                actionButtons = `
                    <div class="mt-3 flex gap-2">
                        <button onclick="closePositionById(${orderId})" 
                                class="flex-1 bg-gradient-to-r from-orange-600 to-orange-500 hover:from-orange-500 hover:to-orange-400 text-white font-bold py-2 px-3 rounded text-xs transition-all">
                            CLOSE POSITION
                        </button>
                    </div>
                `;
            }
            
            let orderIdDisplay = orderId ? `<span class="text-xs text-gray-500">Order #${orderId}</span>` : '';
            
            let tradeHtml = `
                <div class="bg-blue-900/20 border border-${statusColor}-600 rounded-lg p-4 text-sm hover:bg-blue-900/30 transition-all">
                    <div class="flex justify-between items-center mb-3">
                        <div>
                            <span class="font-bold text-${statusColor}-400 text-base">${status}</span>
                            ${orderIdDisplay}
                        </div>
                        <span class="text-gray-400 text-xs">${now}</span>
                    </div>
                    <div class="grid grid-cols-3 gap-3 text-xs">
                        <div class="bg-black/30 p-2 rounded">
                            <span class="text-gray-400 block">Option</span>
                            <span class="text-green-300 font-bold text-base">$${price.toFixed(2)}</span>
                        </div>
                        <div class="bg-black/30 p-2 rounded">
                            <span class="text-gray-400 block">Entry</span>
                            <span class="text-cyan-300 font-bold text-base">$${trigger.toFixed(2)}</span>
                        </div>
                        <div class="bg-black/30 p-2 rounded">
                            <span class="text-gray-400 block">Qty</span>
                            <span class="text-white font-bold text-base">${qty}x</span>
                        </div>
                        <div class="bg-black/30 p-2 rounded">
                            <span class="text-gray-400 block">TP</span>
                            <span class="text-green-300 font-bold">$${tp.toFixed(2)}</span>
                        </div>
                        <div class="bg-black/30 p-2 rounded">
                            <span class="text-gray-400 block">SL</span>
                            <span class="text-red-300 font-bold">$${sl.toFixed(2)}</span>
                        </div>
                    </div>
                    ${actionButtons}
                </div>
            `;
            
            list.insertAdjacentHTML('afterbegin', tradeHtml);
        }

        async function testIBKR() {
            let host = document.getElementById('ibkr-host').value;
            let port = parseInt(document.getElementById('ibkr-port').value);
            let cid = parseInt(document.getElementById('ibkr-cid').value);

            document.getElementById('ibkr-status').innerText = 'Connecting...';
            document.getElementById('ibkr-status').className = 'text-sm text-yellow-400';

            try {
                let res = await fetch('/api/connect_ibkr', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({host: host, port: port, client_id: cid})
                });
                
                let data = await res.json();
                
                if (data.status === 'success') {
                    document.getElementById('ibkr-status').innerText = 'Connected';
                    document.getElementById('ibkr-status').className = 'text-sm text-green-400 font-bold';
                    document.getElementById('status-dot').className = 'status-dot status-connected';
                    alert('IBKR Connected Successfully');
                } else {
                    document.getElementById('ibkr-status').innerText = 'Failed: ' + data.message;
                    document.getElementById('ibkr-status').className = 'text-sm text-red-400';
                    alert('Connection Failed: ' + data.message);
                }
            } catch (e) {
                document.getElementById('ibkr-status').innerText = 'Error: ' + e.message;
                document.getElementById('ibkr-status').className = 'text-sm text-red-400';
                alert('Error: ' + e.message);
            }
        }

        function switchTab(tab) {
            document.querySelectorAll('[id^="tab-"]').forEach(btn => {
                btn.classList.remove('border-cyan-400', 'text-cyan-400');
                btn.classList.add('border-transparent', 'text-gray-400');
            });
            document.getElementById('tab-' + tab).classList.add('border-cyan-400', 'text-cyan-400');
            document.getElementById('tab-' + tab).classList.remove('border-transparent', 'text-gray-400');
            
            document.getElementById('dashboard').classList.add('hidden');
            document.getElementById('trades').classList.add('hidden');
            document.getElementById('settings').classList.add('hidden');
            document.getElementById(tab).classList.remove('hidden');
        }

        async function refreshStatus() {
            try {
                let res = await fetch('/api/status');
                let data = await res.json();
                
                let statusDot = document.getElementById('status-dot');
                if (data.ibkr.status === 'connected') {
                    statusDot.className = 'status-dot status-connected';
                } else {
                    statusDot.className = 'status-dot status-disconnected';
                }
            } catch (e) {
                console.error('Status refresh error:', e);
            }
        }

        function init() {
            initChart();
            renderLadder();
            refreshStatus();
            setInterval(refreshStatus, 5000);
            
            document.getElementById('tp-input').addEventListener('input', updateTradeLevels);
            document.getElementById('sl-input').addEventListener('input', updateTradeLevels);
        }

        window.addEventListener('load', init);
    </script>
</body>
</html>"""

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        self.log_queue.put(record)

class SPYTradingSuite:
    def __init__(self):
        self.log_queue = queue.Queue()
        self.setup_logging()
        self.ib = None
        self.ib_connected = False
        self.config = self.load_config()
        self.spy_price = None
        self.last_ib_error = None
        self.last_order_id = None
        self.trades = {}
        self.orders = {}
        self.local_ip = self.get_local_ip()
        self.webhook_port = self.config.get('webhook_port', 8080)
        self.app = self.create_flask_app()
        self.ib_queue = queue.Queue()
        self.start_ib_thread()
        self.logger.info("SPY Trading Suite v4.3 initialized - TV Price Mode")
    
    def setup_logging(self):
        app_dir = Path.home() / ".spy_trading_suite"
        app_dir.mkdir(exist_ok=True)
        log_dir = app_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / ("trader_" + datetime.now().strftime('%Y%m%d') + ".log")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setFormatter(formatter)
        
        self.logger = logging.getLogger('SPYTradingSuite')
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(file_handler)
        
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setFormatter(formatter)
        self.logger.addHandler(queue_handler)
    
    def load_config(self):
        app_dir = Path.home() / ".spy_trading_suite"
        config_file = app_dir / "config.json"
        
        default = {
            'webhook_port': 8080,
            'ibkr_host': '127.0.0.1',
            'ibkr_port': 7497,
            'ibkr_client_id': 1,
            'tp_dollars': 0.05,
            'sl_dollars': 0.03
        }
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    default.update(json.load(f))
            except:
                pass
        
        return default
    
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def start_ib_thread(self):
        def ib_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            util.patchAsyncio()
            
            while True:
                try:
                    cmd = self.ib_queue.get(timeout=1)
                    if cmd['type'] == 'connect':
                        self._ib_connect(cmd['host'], cmd['port'], cmd['client_id'])
                    elif cmd['type'] == 'disconnect':
                        self._ib_disconnect()
                    elif cmd['type'] == 'trade':
                        self._ib_execute_trade(cmd['params'])
                    elif cmd['type'] == 'cancel':
                        self._ib_cancel_order(cmd['order_id'])
                    elif cmd['type'] == 'close':
                        self._ib_close_position(cmd['trade_id'])
                except queue.Empty:
                    pass
                except Exception as e:
                    self.logger.error(f"IB worker error: {e}")
                    self.last_ib_error = str(e)
        
        threading.Thread(target=ib_worker, daemon=True).start()
    
    def _ib_connect(self, host, port, client_id):
        try:
            self.logger.info(f"Connecting to IBKR {host}:{port} client={client_id}")
            
            if self.ib and self.ib.isConnected():
                self.logger.info("Disconnecting existing connection")
                self.ib.disconnect()
            
            self.ib = IB()
            self.ib.connect(host, port, clientId=client_id, timeout=20)
            
            if self.ib.isConnected():
                self.ib_connected = True
                self.last_ib_error = None
                self.logger.info(f"Connected to IBKR successfully")
            else:
                raise Exception("Connection failed")
                
        except Exception as e:
            self.ib_connected = False
            self.last_ib_error = str(e)
            self.logger.error(f"IBKR connection error: {e}")
    
    def _ib_disconnect(self):
        try:
            if self.ib:
                self.ib.disconnect()
                self.ib = None
                self.ib_connected = False
                self.logger.info("Disconnected from IBKR")
        except Exception as e:
            self.logger.error(f"Disconnect error: {e}")
    
    def _ib_execute_trade(self, params):
        try:
            self.logger.info(f"Executing trade with params: {params}")
            
            if not self.ib_connected or not self.ib:
                raise Exception("IBKR not connected")
            
            strike = params.get('strike')
            expiry = params.get('expiry')
            opt_type = params.get('type', 'C')
            price = params.get('price')
            qty = params.get('qty', 1)
            
            self.logger.info(f"Creating option: SPY {expiry} ${strike} {opt_type}")
            option = Option('SPY', expiry, strike, opt_type, 'SMART')
            
            self.logger.info(f"Qualifying contract...")
            contracts = self.ib.qualifyContracts(option)
            
            if not contracts:
                raise Exception(f"Contract not found: SPY {expiry} ${strike} {opt_type}. Check if this strike/date exists in IBKR.")
            
            qualified_option = contracts[0]
            self.logger.info(f"Contract qualified: {qualified_option}")
            
            self.logger.info(f"Creating order: BUY {qty} @ ${price}")
            order = LimitOrder('BUY', qty, price)
            
            self.logger.info(f"Placing order with IBKR...")
            trade = self.ib.placeOrder(qualified_option, order)
            
            order_id = trade.order.orderId
            self.orders[order_id] = trade
            self.last_order_id = order_id  # Store for API response
            
            self.logger.info(f"[SUCCESS] Order placed: {qty}x ${strike}{opt_type} @ ${price} (Order ID: {order_id})")
            
            return order_id
        except Exception as e:
            self.logger.error(f"[FAILED] Trade execution error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.last_ib_error = str(e)
            self.last_order_id = None  # Clear on error
            raise
    
    def _ib_cancel_order(self, order_id):
        try:
            if order_id in self.orders:
                trade = self.orders[order_id]
                self.ib.cancelOrder(trade.order)
                del self.orders[order_id]
                self.logger.info(f"Order {order_id} cancelled")
        except Exception as e:
            self.logger.error(f"Cancel error: {e}")
    
    def _ib_close_position(self, trade_id):
        try:
            if trade_id in self.trades:
                del self.trades[trade_id]
                self.logger.info(f"Position {trade_id} closed")
        except Exception as e:
            self.logger.error(f"Close error: {e}")
    
    def create_flask_app(self):
        app = Flask(__name__)
        app.logger.setLevel(logging.ERROR)
        
        @app.route('/')
        def index():
            return HTML
        
        @app.route('/api/status')
        def get_status():
            return jsonify({
                'server': {'status': 'running', 'port': self.webhook_port, 'version': VERSION},
                'ibkr': {
                    'status': 'connected' if self.ib_connected else 'disconnected',
                    'error': self.last_ib_error
                },
                'spy_price': round(self.spy_price, 2) if self.spy_price else None
            })
        
        @app.route('/api/update_price', methods=['POST'])
        def update_price():
            try:
                data = request.get_json()
                price = data.get('price')
                if price:
                    self.spy_price = price
                    self.logger.debug(f"Price updated from TV: ${price:.2f}")
                return jsonify({'status': 'success'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/execute_trade', methods=['POST'])
        def execute_trade():
            try:
                data = request.get_json()
                
                if not self.ib_connected:
                    return jsonify({'status': 'error', 'message': 'IBKR not connected'}), 400
                
                # Clear any previous error and order ID
                self.last_ib_error = None
                self.last_order_id = None
                
                # Put trade in queue for IBKR thread to process
                self.ib_queue.put({'type': 'trade', 'params': data})
                
                # Wait for order to be processed
                import time
                time.sleep(2)
                
                # Check if there was an error
                if self.last_ib_error:
                    return jsonify({'status': 'error', 'message': self.last_ib_error}), 500
                
                # Check if we got an order ID
                if not self.last_order_id:
                    return jsonify({'status': 'error', 'message': 'Order failed - no order ID received'}), 500
                
                msg = f'Order placed: {data.get("qty")}x @ ${data.get("price")}'
                self.logger.info(msg)
                return jsonify({
                    'status': 'success', 
                    'message': msg, 
                    'order_id': self.last_order_id
                })
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/cancel_order', methods=['POST'])
        def cancel_order():
            try:
                data = request.get_json()
                self.ib_queue.put({'type': 'cancel', 'order_id': data.get('order_id')})
                return jsonify({'status': 'success', 'message': 'Order cancelled'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/get_orders', methods=['GET'])
        def get_orders():
            """Get list of active orders and positions"""
            try:
                if not self.ib_connected:
                    return jsonify({'orders': [], 'positions': []})
                
                orders_list = []
                for order_id, trade in self.orders.items():
                    orders_list.append({
                        'order_id': order_id,
                        'symbol': trade.contract.symbol,
                        'strike': getattr(trade.contract, 'strike', None),
                        'expiry': getattr(trade.contract, 'lastTradeDateOrContractMonth', None),
                        'right': getattr(trade.contract, 'right', None),
                        'action': trade.order.action,
                        'quantity': trade.order.totalQuantity,
                        'limit_price': trade.order.lmtPrice,
                        'status': trade.orderStatus.status
                    })
                
                positions_list = []
                for trade_id, trade_data in self.trades.items():
                    positions_list.append({
                        'trade_id': trade_id,
                        'data': trade_data
                    })
                
                return jsonify({
                    'status': 'success',
                    'orders': orders_list,
                    'positions': positions_list
                })
            except Exception as e:
                self.logger.error(f"Error getting orders: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/close_position', methods=['POST'])
        def close_position():
            try:
                data = request.get_json()
                self.ib_queue.put({'type': 'close', 'trade_id': data.get('trade_id')})
                return jsonify({'status': 'success', 'message': 'Position closed'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/connect_ibkr', methods=['POST'])
        def connect_ibkr():
            try:
                data = request.get_json()
                host = data.get('host', '127.0.0.1')
                port = int(data.get('port', 7497))
                client_id = int(data.get('client_id', 1))
                
                self.ib_queue.put({
                    'type': 'connect',
                    'host': host,
                    'port': port,
                    'client_id': client_id
                })
                
                import time
                time.sleep(3)
                
                if self.ib_connected:
                    return jsonify({'status': 'success', 'message': 'Connected'})
                else:
                    error_msg = self.last_ib_error or 'Connection failed'
                    return jsonify({'status': 'error', 'message': error_msg}), 500
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/get_option_chain', methods=['POST'])
        def get_option_chain():
            """Get available option expirations and strikes for SPY"""
            try:
                if not self.ib_connected:
                    return jsonify({'status': 'error', 'message': 'IBKR not connected'}), 400
                
                # Get SPY stock contract
                stock = Stock('SPY', 'SMART', 'USD')
                self.ib.qualifyContracts(stock)
                
                # Request option chain
                chains = self.ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
                
                if not chains:
                    return jsonify({'status': 'error', 'message': 'No option chains found'}), 404
                
                # Get the first chain (usually the main one)
                chain = chains[0]
                
                # Get available expirations and strikes
                expirations = sorted(chain.expirations)[:10]  # First 10 expirations
                strikes = sorted(chain.strikes)
                
                # Find strikes near current price (if we have it)
                if self.spy_price:
                    # Get strikes within $50 of current price
                    nearby_strikes = [s for s in strikes if abs(s - self.spy_price) <= 50]
                    strikes_to_show = sorted(nearby_strikes)[:20]  # Show 20 strikes near money
                else:
                    strikes_to_show = strikes[:20]  # Just show first 20
                
                return jsonify({
                    'status': 'success',
                    'expirations': expirations,
                    'strikes': strikes_to_show,
                    'current_spy_price': self.spy_price,
                    'exchange': chain.exchange,
                    'message': f'Found {len(expirations)} expirations and {len(strikes_to_show)} nearby strikes'
                })
                
            except Exception as e:
                self.logger.error(f"Error fetching option chain: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/verify_contract', methods=['POST'])
        def verify_contract():
            """Verify if a specific option contract exists"""
            try:
                if not self.ib_connected:
                    return jsonify({'status': 'error', 'message': 'IBKR not connected'}), 400
                
                data = request.get_json()
                strike = data.get('strike')
                expiry = data.get('expiry')
                opt_type = data.get('type', 'C')
                
                option = Option('SPY', expiry, strike, opt_type, 'SMART')
                contracts = self.ib.qualifyContracts(option)
                
                if contracts:
                    contract = contracts[0]
                    return jsonify({
                        'status': 'success',
                        'message': 'Contract found!',
                        'contract': {
                            'symbol': contract.symbol,
                            'strike': contract.strike,
                            'expiry': contract.lastTradeDateOrContractMonth,
                            'right': contract.right,
                            'exchange': contract.exchange,
                            'conId': contract.conId
                        }
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': f'Contract not found: SPY {expiry} ${strike} {opt_type}'
                    }), 404
                    
            except Exception as e:
                self.logger.error(f"Error verifying contract: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @app.route('/api/disconnect_ibkr', methods=['POST'])
        def disconnect_ibkr():
            try:
                self.ib_queue.put({'type': 'disconnect'})
                return jsonify({'status': 'success', 'message': 'Disconnected'})
            except Exception as e:
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        return app
    
    def run(self, port=8080):
        print("\n" + "="*80)
        print(f"SPY Trading Suite v{VERSION} - TRADINGVIEW PRICE EDITION")
        print("="*80)
        print(f"\nURL: http://{self.local_ip}:{port}")
        print("\nKEY FEATURES:")
        print("  - Price from TradingView chart (no IBKR data subscription needed)")
        print("  - IBKR only for order execution")
        print("  - Manual price override available in settings")
        print("  - All calculations based on TV chart price")
        print("  - Enhanced mid-price highlighting")
        print("  - Real-time ladder updates")
        print("\nPress CTRL+C to quit\n")
        
        self.logger.info(f"Starting on {self.local_ip}:{port}")
        self.app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)


def main():
    try:
        suite = SPYTradingSuite()
        suite.run(port=8080)
    except KeyboardInterrupt:
        print("\n\nServer stopped")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
