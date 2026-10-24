// Package data embeds fixtures transcribed from Northstar's mobile marketData.ts.
package data

import _ "embed"

//go:embed market-assets.json
var Assets []byte

//go:embed market-indexes.json
var Indexes []byte
