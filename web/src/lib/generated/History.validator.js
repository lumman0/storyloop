// Generated from api/contracts.py.
"use strict";
export const validate = validate20;
export default validate20;
const schema31 = {"$defs":{"ActionOption":{"additionalProperties":false,"properties":{"input":{"title":"Input","type":"string"},"label":{"title":"Label","type":"string"}},"required":["label","input"],"title":"ActionOption","type":"object"},"HistoryTurn":{"additionalProperties":false,"properties":{"input":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Input"},"request_id":{"title":"Request Id","type":"string"},"response":{"$ref":"#/$defs/View"}},"required":["request_id","input","response"],"title":"HistoryTurn","type":"object"},"Interaction":{"additionalProperties":false,"properties":{"id":{"title":"Id","type":"string"},"kind":{"enum":["choice","message","continue"],"title":"Kind","type":"string"},"label":{"default":null,"title":"Label","type":"string"},"options":{"items":{"$ref":"#/$defs/InteractionOption"},"title":"Options","type":"array"},"prompt":{"title":"Prompt","type":"string"}},"required":["id","kind","prompt","options"],"title":"Interaction","type":"object"},"InteractionOption":{"additionalProperties":false,"properties":{"enabled":{"title":"Enabled","type":"boolean"},"id":{"title":"Id","type":"string"},"label":{"title":"Label","type":"string"},"requires_text":{"title":"Requires Text","type":"boolean"}},"required":["id","label","enabled","requires_text"],"title":"InteractionOption","type":"object"},"StatusField":{"additionalProperties":false,"properties":{"id":{"title":"Id","type":"string"},"label":{"title":"Label","type":"string"},"max":{"default":null,"title":"Max","type":"integer"},"min":{"default":null,"title":"Min","type":"integer"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"boolean"}],"title":"Value"}},"required":["id","label","value"],"title":"StatusField","type":"object"},"StorySegment":{"additionalProperties":false,"properties":{"kind":{"enum":["narration","scene","dialogue","message","prompt","time"],"title":"Kind","type":"string"},"speaker_id":{"default":null,"title":"Speaker Id","type":"string"},"speaker_name":{"default":null,"title":"Speaker Name","type":"string"},"text":{"title":"Text","type":"string"}},"required":["kind","text"],"title":"StorySegment","type":"object"},"TurnBilling":{"additionalProperties":false,"properties":{"balance_milli_points":{"title":"Balance Milli Points","type":"integer"},"balance_points":{"title":"Balance Points","type":"string"},"charged_milli_points":{"title":"Charged Milli Points","type":"integer"},"charged_points":{"title":"Charged Points","type":"string"},"input_tokens":{"title":"Input Tokens","type":"integer"},"model_calls":{"title":"Model Calls","type":"integer"},"output_tokens":{"title":"Output Tokens","type":"integer"},"usage_cost_milli_points":{"title":"Usage Cost Milli Points","type":"integer"}},"required":["charged_milli_points","charged_points","usage_cost_milli_points","balance_milli_points","balance_points","input_tokens","output_tokens","model_calls"],"title":"TurnBilling","type":"object"},"View":{"additionalProperties":false,"properties":{"action_options":{"items":{"$ref":"#/$defs/ActionOption"},"title":"Action Options","type":"array"},"billing":{"$ref":"#/$defs/TurnBilling","default":null},"body":{"title":"Body","type":"string"},"catalog_id":{"title":"Catalog Id","type":"string"},"complete":{"title":"Complete","type":"boolean"},"day":{"anyOf":[{"type":"integer"},{"type":"null"}],"title":"Day"},"game_id":{"title":"Game Id","type":"string"},"interaction":{"anyOf":[{"$ref":"#/$defs/Interaction"},{"type":"null"}]},"mode":{"enum":["campaign","freeform"],"title":"Mode","type":"string"},"opening":{"title":"Opening","type":"string"},"presentation_mode":{"enum":["interactive","novel"],"title":"Presentation Mode","type":"string"},"segments":{"items":{"$ref":"#/$defs/StorySegment"},"title":"Segments","type":"array"},"state_version":{"title":"State Version","type":"integer"},"status_fields":{"items":{"$ref":"#/$defs/StatusField"},"title":"Status Fields","type":"array"},"suggestions":{"items":{"type":"string"},"title":"Suggestions","type":"array"},"tick":{"title":"Tick","type":"integer"},"time_of_day":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Time Of Day"},"turn_id":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Turn Id"}},"required":["game_id","catalog_id","mode","presentation_mode","opening","body","segments","suggestions","action_options","status_fields","interaction","tick","state_version","day","time_of_day","complete","turn_id"],"title":"View","type":"object"}},"additionalProperties":false,"properties":{"game_id":{"title":"Game Id","type":"string"},"intro":{"$ref":"#/$defs/View"},"turns":{"items":{"$ref":"#/$defs/HistoryTurn"},"title":"Turns","type":"array"}},"required":["game_id","intro","turns"],"title":"History","type":"object"};
const schema32 = {"additionalProperties":false,"properties":{"action_options":{"items":{"$ref":"#/$defs/ActionOption"},"title":"Action Options","type":"array"},"billing":{"$ref":"#/$defs/TurnBilling","default":null},"body":{"title":"Body","type":"string"},"catalog_id":{"title":"Catalog Id","type":"string"},"complete":{"title":"Complete","type":"boolean"},"day":{"anyOf":[{"type":"integer"},{"type":"null"}],"title":"Day"},"game_id":{"title":"Game Id","type":"string"},"interaction":{"anyOf":[{"$ref":"#/$defs/Interaction"},{"type":"null"}]},"mode":{"enum":["campaign","freeform"],"title":"Mode","type":"string"},"opening":{"title":"Opening","type":"string"},"presentation_mode":{"enum":["interactive","novel"],"title":"Presentation Mode","type":"string"},"segments":{"items":{"$ref":"#/$defs/StorySegment"},"title":"Segments","type":"array"},"state_version":{"title":"State Version","type":"integer"},"status_fields":{"items":{"$ref":"#/$defs/StatusField"},"title":"Status Fields","type":"array"},"suggestions":{"items":{"type":"string"},"title":"Suggestions","type":"array"},"tick":{"title":"Tick","type":"integer"},"time_of_day":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Time Of Day"},"turn_id":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Turn Id"}},"required":["game_id","catalog_id","mode","presentation_mode","opening","body","segments","suggestions","action_options","status_fields","interaction","tick","state_version","day","time_of_day","complete","turn_id"],"title":"View","type":"object"};
const schema33 = {"additionalProperties":false,"properties":{"input":{"title":"Input","type":"string"},"label":{"title":"Label","type":"string"}},"required":["label","input"],"title":"ActionOption","type":"object"};
const schema34 = {"additionalProperties":false,"properties":{"balance_milli_points":{"title":"Balance Milli Points","type":"integer"},"balance_points":{"title":"Balance Points","type":"string"},"charged_milli_points":{"title":"Charged Milli Points","type":"integer"},"charged_points":{"title":"Charged Points","type":"string"},"input_tokens":{"title":"Input Tokens","type":"integer"},"model_calls":{"title":"Model Calls","type":"integer"},"output_tokens":{"title":"Output Tokens","type":"integer"},"usage_cost_milli_points":{"title":"Usage Cost Milli Points","type":"integer"}},"required":["charged_milli_points","charged_points","usage_cost_milli_points","balance_milli_points","balance_points","input_tokens","output_tokens","model_calls"],"title":"TurnBilling","type":"object"};
const schema37 = {"additionalProperties":false,"properties":{"kind":{"enum":["narration","scene","dialogue","message","prompt","time"],"title":"Kind","type":"string"},"speaker_id":{"default":null,"title":"Speaker Id","type":"string"},"speaker_name":{"default":null,"title":"Speaker Name","type":"string"},"text":{"title":"Text","type":"string"}},"required":["kind","text"],"title":"StorySegment","type":"object"};
const schema38 = {"additionalProperties":false,"properties":{"id":{"title":"Id","type":"string"},"label":{"title":"Label","type":"string"},"max":{"default":null,"title":"Max","type":"integer"},"min":{"default":null,"title":"Min","type":"integer"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"boolean"}],"title":"Value"}},"required":["id","label","value"],"title":"StatusField","type":"object"};
const func1 = Object.prototype.hasOwnProperty;
const schema35 = {"additionalProperties":false,"properties":{"id":{"title":"Id","type":"string"},"kind":{"enum":["choice","message","continue"],"title":"Kind","type":"string"},"label":{"default":null,"title":"Label","type":"string"},"options":{"items":{"$ref":"#/$defs/InteractionOption"},"title":"Options","type":"array"},"prompt":{"title":"Prompt","type":"string"}},"required":["id","kind","prompt","options"],"title":"Interaction","type":"object"};
const schema36 = {"additionalProperties":false,"properties":{"enabled":{"title":"Enabled","type":"boolean"},"id":{"title":"Id","type":"string"},"label":{"title":"Label","type":"string"},"requires_text":{"title":"Requires Text","type":"boolean"}},"required":["id","label","enabled","requires_text"],"title":"InteractionOption","type":"object"};

function validate22(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate22.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(errors === 0){
if(data && typeof data == "object" && !Array.isArray(data)){
let missing0;
if(((((data.id === undefined) && (missing0 = "id")) || ((data.kind === undefined) && (missing0 = "kind"))) || ((data.prompt === undefined) && (missing0 = "prompt"))) || ((data.options === undefined) && (missing0 = "options"))){
validate22.errors = [{instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: missing0},message:"must have required property '"+missing0+"'"}];
return false;
}
else {
const _errs1 = errors;
for(const key0 in data){
if(!(((((key0 === "id") || (key0 === "kind")) || (key0 === "label")) || (key0 === "options")) || (key0 === "prompt"))){
validate22.errors = [{instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs1 === errors){
if(data.id !== undefined){
const _errs2 = errors;
if(typeof data.id !== "string"){
validate22.errors = [{instancePath:instancePath+"/id",schemaPath:"#/properties/id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs2 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.kind !== undefined){
let data1 = data.kind;
const _errs4 = errors;
if(typeof data1 !== "string"){
validate22.errors = [{instancePath:instancePath+"/kind",schemaPath:"#/properties/kind/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
if(!(((data1 === "choice") || (data1 === "message")) || (data1 === "continue"))){
validate22.errors = [{instancePath:instancePath+"/kind",schemaPath:"#/properties/kind/enum",keyword:"enum",params:{allowedValues: schema35.properties.kind.enum},message:"must be equal to one of the allowed values"}];
return false;
}
var valid0 = _errs4 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.label !== undefined){
const _errs6 = errors;
if(typeof data.label !== "string"){
validate22.errors = [{instancePath:instancePath+"/label",schemaPath:"#/properties/label/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs6 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.options !== undefined){
let data3 = data.options;
const _errs8 = errors;
if(errors === _errs8){
if(Array.isArray(data3)){
var valid1 = true;
const len0 = data3.length;
for(let i0=0; i0<len0; i0++){
let data4 = data3[i0];
const _errs10 = errors;
const _errs11 = errors;
if(errors === _errs11){
if(data4 && typeof data4 == "object" && !Array.isArray(data4)){
let missing1;
if(((((data4.id === undefined) && (missing1 = "id")) || ((data4.label === undefined) && (missing1 = "label"))) || ((data4.enabled === undefined) && (missing1 = "enabled"))) || ((data4.requires_text === undefined) && (missing1 = "requires_text"))){
validate22.errors = [{instancePath:instancePath+"/options/" + i0,schemaPath:"#/$defs/InteractionOption/required",keyword:"required",params:{missingProperty: missing1},message:"must have required property '"+missing1+"'"}];
return false;
}
else {
const _errs13 = errors;
for(const key1 in data4){
if(!((((key1 === "enabled") || (key1 === "id")) || (key1 === "label")) || (key1 === "requires_text"))){
validate22.errors = [{instancePath:instancePath+"/options/" + i0,schemaPath:"#/$defs/InteractionOption/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs13 === errors){
if(data4.enabled !== undefined){
const _errs14 = errors;
if(typeof data4.enabled !== "boolean"){
validate22.errors = [{instancePath:instancePath+"/options/" + i0+"/enabled",schemaPath:"#/$defs/InteractionOption/properties/enabled/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"}];
return false;
}
var valid3 = _errs14 === errors;
}
else {
var valid3 = true;
}
if(valid3){
if(data4.id !== undefined){
const _errs16 = errors;
if(typeof data4.id !== "string"){
validate22.errors = [{instancePath:instancePath+"/options/" + i0+"/id",schemaPath:"#/$defs/InteractionOption/properties/id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid3 = _errs16 === errors;
}
else {
var valid3 = true;
}
if(valid3){
if(data4.label !== undefined){
const _errs18 = errors;
if(typeof data4.label !== "string"){
validate22.errors = [{instancePath:instancePath+"/options/" + i0+"/label",schemaPath:"#/$defs/InteractionOption/properties/label/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid3 = _errs18 === errors;
}
else {
var valid3 = true;
}
if(valid3){
if(data4.requires_text !== undefined){
const _errs20 = errors;
if(typeof data4.requires_text !== "boolean"){
validate22.errors = [{instancePath:instancePath+"/options/" + i0+"/requires_text",schemaPath:"#/$defs/InteractionOption/properties/requires_text/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"}];
return false;
}
var valid3 = _errs20 === errors;
}
else {
var valid3 = true;
}
}
}
}
}
}
}
else {
validate22.errors = [{instancePath:instancePath+"/options/" + i0,schemaPath:"#/$defs/InteractionOption/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
var valid1 = _errs10 === errors;
if(!valid1){
break;
}
}
}
else {
validate22.errors = [{instancePath:instancePath+"/options",schemaPath:"#/properties/options/type",keyword:"type",params:{type: "array"},message:"must be array"}];
return false;
}
}
var valid0 = _errs8 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.prompt !== undefined){
const _errs22 = errors;
if(typeof data.prompt !== "string"){
validate22.errors = [{instancePath:instancePath+"/prompt",schemaPath:"#/properties/prompt/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs22 === errors;
}
else {
var valid0 = true;
}
}
}
}
}
}
}
}
else {
validate22.errors = [{instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
validate22.errors = vErrors;
return errors === 0;
}
validate22.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate21(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate21.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(errors === 0){
if(data && typeof data == "object" && !Array.isArray(data)){
let missing0;
if((((((((((((((((((data.game_id === undefined) && (missing0 = "game_id")) || ((data.catalog_id === undefined) && (missing0 = "catalog_id"))) || ((data.mode === undefined) && (missing0 = "mode"))) || ((data.presentation_mode === undefined) && (missing0 = "presentation_mode"))) || ((data.opening === undefined) && (missing0 = "opening"))) || ((data.body === undefined) && (missing0 = "body"))) || ((data.segments === undefined) && (missing0 = "segments"))) || ((data.suggestions === undefined) && (missing0 = "suggestions"))) || ((data.action_options === undefined) && (missing0 = "action_options"))) || ((data.status_fields === undefined) && (missing0 = "status_fields"))) || ((data.interaction === undefined) && (missing0 = "interaction"))) || ((data.tick === undefined) && (missing0 = "tick"))) || ((data.state_version === undefined) && (missing0 = "state_version"))) || ((data.day === undefined) && (missing0 = "day"))) || ((data.time_of_day === undefined) && (missing0 = "time_of_day"))) || ((data.complete === undefined) && (missing0 = "complete"))) || ((data.turn_id === undefined) && (missing0 = "turn_id"))){
validate21.errors = [{instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: missing0},message:"must have required property '"+missing0+"'"}];
return false;
}
else {
const _errs1 = errors;
for(const key0 in data){
if(!(func1.call(schema32.properties, key0))){
validate21.errors = [{instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs1 === errors){
if(data.action_options !== undefined){
let data0 = data.action_options;
const _errs2 = errors;
if(errors === _errs2){
if(Array.isArray(data0)){
var valid1 = true;
const len0 = data0.length;
for(let i0=0; i0<len0; i0++){
let data1 = data0[i0];
const _errs4 = errors;
const _errs5 = errors;
if(errors === _errs5){
if(data1 && typeof data1 == "object" && !Array.isArray(data1)){
let missing1;
if(((data1.label === undefined) && (missing1 = "label")) || ((data1.input === undefined) && (missing1 = "input"))){
validate21.errors = [{instancePath:instancePath+"/action_options/" + i0,schemaPath:"#/$defs/ActionOption/required",keyword:"required",params:{missingProperty: missing1},message:"must have required property '"+missing1+"'"}];
return false;
}
else {
const _errs7 = errors;
for(const key1 in data1){
if(!((key1 === "input") || (key1 === "label"))){
validate21.errors = [{instancePath:instancePath+"/action_options/" + i0,schemaPath:"#/$defs/ActionOption/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs7 === errors){
if(data1.input !== undefined){
const _errs8 = errors;
if(typeof data1.input !== "string"){
validate21.errors = [{instancePath:instancePath+"/action_options/" + i0+"/input",schemaPath:"#/$defs/ActionOption/properties/input/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid3 = _errs8 === errors;
}
else {
var valid3 = true;
}
if(valid3){
if(data1.label !== undefined){
const _errs10 = errors;
if(typeof data1.label !== "string"){
validate21.errors = [{instancePath:instancePath+"/action_options/" + i0+"/label",schemaPath:"#/$defs/ActionOption/properties/label/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid3 = _errs10 === errors;
}
else {
var valid3 = true;
}
}
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/action_options/" + i0,schemaPath:"#/$defs/ActionOption/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
var valid1 = _errs4 === errors;
if(!valid1){
break;
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/action_options",schemaPath:"#/properties/action_options/type",keyword:"type",params:{type: "array"},message:"must be array"}];
return false;
}
}
var valid0 = _errs2 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.billing !== undefined){
let data4 = data.billing;
const _errs12 = errors;
const _errs13 = errors;
if(errors === _errs13){
if(data4 && typeof data4 == "object" && !Array.isArray(data4)){
let missing2;
if(((((((((data4.charged_milli_points === undefined) && (missing2 = "charged_milli_points")) || ((data4.charged_points === undefined) && (missing2 = "charged_points"))) || ((data4.usage_cost_milli_points === undefined) && (missing2 = "usage_cost_milli_points"))) || ((data4.balance_milli_points === undefined) && (missing2 = "balance_milli_points"))) || ((data4.balance_points === undefined) && (missing2 = "balance_points"))) || ((data4.input_tokens === undefined) && (missing2 = "input_tokens"))) || ((data4.output_tokens === undefined) && (missing2 = "output_tokens"))) || ((data4.model_calls === undefined) && (missing2 = "model_calls"))){
validate21.errors = [{instancePath:instancePath+"/billing",schemaPath:"#/$defs/TurnBilling/required",keyword:"required",params:{missingProperty: missing2},message:"must have required property '"+missing2+"'"}];
return false;
}
else {
const _errs15 = errors;
for(const key2 in data4){
if(!((((((((key2 === "balance_milli_points") || (key2 === "balance_points")) || (key2 === "charged_milli_points")) || (key2 === "charged_points")) || (key2 === "input_tokens")) || (key2 === "model_calls")) || (key2 === "output_tokens")) || (key2 === "usage_cost_milli_points"))){
validate21.errors = [{instancePath:instancePath+"/billing",schemaPath:"#/$defs/TurnBilling/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key2},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs15 === errors){
if(data4.balance_milli_points !== undefined){
let data5 = data4.balance_milli_points;
const _errs16 = errors;
if(!(((typeof data5 == "number") && (!(data5 % 1) && !isNaN(data5))) && (isFinite(data5)))){
validate21.errors = [{instancePath:instancePath+"/billing/balance_milli_points",schemaPath:"#/$defs/TurnBilling/properties/balance_milli_points/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid5 = _errs16 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.balance_points !== undefined){
const _errs18 = errors;
if(typeof data4.balance_points !== "string"){
validate21.errors = [{instancePath:instancePath+"/billing/balance_points",schemaPath:"#/$defs/TurnBilling/properties/balance_points/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid5 = _errs18 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.charged_milli_points !== undefined){
let data7 = data4.charged_milli_points;
const _errs20 = errors;
if(!(((typeof data7 == "number") && (!(data7 % 1) && !isNaN(data7))) && (isFinite(data7)))){
validate21.errors = [{instancePath:instancePath+"/billing/charged_milli_points",schemaPath:"#/$defs/TurnBilling/properties/charged_milli_points/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid5 = _errs20 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.charged_points !== undefined){
const _errs22 = errors;
if(typeof data4.charged_points !== "string"){
validate21.errors = [{instancePath:instancePath+"/billing/charged_points",schemaPath:"#/$defs/TurnBilling/properties/charged_points/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid5 = _errs22 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.input_tokens !== undefined){
let data9 = data4.input_tokens;
const _errs24 = errors;
if(!(((typeof data9 == "number") && (!(data9 % 1) && !isNaN(data9))) && (isFinite(data9)))){
validate21.errors = [{instancePath:instancePath+"/billing/input_tokens",schemaPath:"#/$defs/TurnBilling/properties/input_tokens/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid5 = _errs24 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.model_calls !== undefined){
let data10 = data4.model_calls;
const _errs26 = errors;
if(!(((typeof data10 == "number") && (!(data10 % 1) && !isNaN(data10))) && (isFinite(data10)))){
validate21.errors = [{instancePath:instancePath+"/billing/model_calls",schemaPath:"#/$defs/TurnBilling/properties/model_calls/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid5 = _errs26 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.output_tokens !== undefined){
let data11 = data4.output_tokens;
const _errs28 = errors;
if(!(((typeof data11 == "number") && (!(data11 % 1) && !isNaN(data11))) && (isFinite(data11)))){
validate21.errors = [{instancePath:instancePath+"/billing/output_tokens",schemaPath:"#/$defs/TurnBilling/properties/output_tokens/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid5 = _errs28 === errors;
}
else {
var valid5 = true;
}
if(valid5){
if(data4.usage_cost_milli_points !== undefined){
let data12 = data4.usage_cost_milli_points;
const _errs30 = errors;
if(!(((typeof data12 == "number") && (!(data12 % 1) && !isNaN(data12))) && (isFinite(data12)))){
validate21.errors = [{instancePath:instancePath+"/billing/usage_cost_milli_points",schemaPath:"#/$defs/TurnBilling/properties/usage_cost_milli_points/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid5 = _errs30 === errors;
}
else {
var valid5 = true;
}
}
}
}
}
}
}
}
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/billing",schemaPath:"#/$defs/TurnBilling/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
var valid0 = _errs12 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.body !== undefined){
const _errs32 = errors;
if(typeof data.body !== "string"){
validate21.errors = [{instancePath:instancePath+"/body",schemaPath:"#/properties/body/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs32 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.catalog_id !== undefined){
const _errs34 = errors;
if(typeof data.catalog_id !== "string"){
validate21.errors = [{instancePath:instancePath+"/catalog_id",schemaPath:"#/properties/catalog_id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs34 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.complete !== undefined){
const _errs36 = errors;
if(typeof data.complete !== "boolean"){
validate21.errors = [{instancePath:instancePath+"/complete",schemaPath:"#/properties/complete/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"}];
return false;
}
var valid0 = _errs36 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.day !== undefined){
let data16 = data.day;
const _errs38 = errors;
const _errs39 = errors;
let valid6 = false;
const _errs40 = errors;
if(!(((typeof data16 == "number") && (!(data16 % 1) && !isNaN(data16))) && (isFinite(data16)))){
const err0 = {instancePath:instancePath+"/day",schemaPath:"#/properties/day/anyOf/0/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
var _valid0 = _errs40 === errors;
valid6 = valid6 || _valid0;
const _errs42 = errors;
if(data16 !== null){
const err1 = {instancePath:instancePath+"/day",schemaPath:"#/properties/day/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
var _valid0 = _errs42 === errors;
valid6 = valid6 || _valid0;
if(!valid6){
const err2 = {instancePath:instancePath+"/day",schemaPath:"#/properties/day/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
validate21.errors = vErrors;
return false;
}
else {
errors = _errs39;
if(vErrors !== null){
if(_errs39){
vErrors.length = _errs39;
}
else {
vErrors = null;
}
}
}
var valid0 = _errs38 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.game_id !== undefined){
const _errs44 = errors;
if(typeof data.game_id !== "string"){
validate21.errors = [{instancePath:instancePath+"/game_id",schemaPath:"#/properties/game_id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs44 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.interaction !== undefined){
let data18 = data.interaction;
const _errs46 = errors;
const _errs47 = errors;
let valid7 = false;
const _errs48 = errors;
if(!(validate22(data18, {instancePath:instancePath+"/interaction",parentData:data,parentDataProperty:"interaction",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate22.errors : vErrors.concat(validate22.errors);
errors = vErrors.length;
}
var _valid1 = _errs48 === errors;
valid7 = valid7 || _valid1;
const _errs49 = errors;
if(data18 !== null){
const err3 = {instancePath:instancePath+"/interaction",schemaPath:"#/properties/interaction/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
var _valid1 = _errs49 === errors;
valid7 = valid7 || _valid1;
if(!valid7){
const err4 = {instancePath:instancePath+"/interaction",schemaPath:"#/properties/interaction/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
validate21.errors = vErrors;
return false;
}
else {
errors = _errs47;
if(vErrors !== null){
if(_errs47){
vErrors.length = _errs47;
}
else {
vErrors = null;
}
}
}
var valid0 = _errs46 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.mode !== undefined){
let data19 = data.mode;
const _errs51 = errors;
if(typeof data19 !== "string"){
validate21.errors = [{instancePath:instancePath+"/mode",schemaPath:"#/properties/mode/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
if(!((data19 === "campaign") || (data19 === "freeform"))){
validate21.errors = [{instancePath:instancePath+"/mode",schemaPath:"#/properties/mode/enum",keyword:"enum",params:{allowedValues: schema32.properties.mode.enum},message:"must be equal to one of the allowed values"}];
return false;
}
var valid0 = _errs51 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.opening !== undefined){
const _errs53 = errors;
if(typeof data.opening !== "string"){
validate21.errors = [{instancePath:instancePath+"/opening",schemaPath:"#/properties/opening/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs53 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.presentation_mode !== undefined){
let data21 = data.presentation_mode;
const _errs55 = errors;
if(typeof data21 !== "string"){
validate21.errors = [{instancePath:instancePath+"/presentation_mode",schemaPath:"#/properties/presentation_mode/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
if(!((data21 === "interactive") || (data21 === "novel"))){
validate21.errors = [{instancePath:instancePath+"/presentation_mode",schemaPath:"#/properties/presentation_mode/enum",keyword:"enum",params:{allowedValues: schema32.properties.presentation_mode.enum},message:"must be equal to one of the allowed values"}];
return false;
}
var valid0 = _errs55 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.segments !== undefined){
let data22 = data.segments;
const _errs57 = errors;
if(errors === _errs57){
if(Array.isArray(data22)){
var valid8 = true;
const len1 = data22.length;
for(let i1=0; i1<len1; i1++){
let data23 = data22[i1];
const _errs59 = errors;
const _errs60 = errors;
if(errors === _errs60){
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
let missing3;
if(((data23.kind === undefined) && (missing3 = "kind")) || ((data23.text === undefined) && (missing3 = "text"))){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1,schemaPath:"#/$defs/StorySegment/required",keyword:"required",params:{missingProperty: missing3},message:"must have required property '"+missing3+"'"}];
return false;
}
else {
const _errs62 = errors;
for(const key3 in data23){
if(!((((key3 === "kind") || (key3 === "speaker_id")) || (key3 === "speaker_name")) || (key3 === "text"))){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1,schemaPath:"#/$defs/StorySegment/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key3},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs62 === errors){
if(data23.kind !== undefined){
let data24 = data23.kind;
const _errs63 = errors;
if(typeof data24 !== "string"){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1+"/kind",schemaPath:"#/$defs/StorySegment/properties/kind/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
if(!((((((data24 === "narration") || (data24 === "scene")) || (data24 === "dialogue")) || (data24 === "message")) || (data24 === "prompt")) || (data24 === "time"))){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1+"/kind",schemaPath:"#/$defs/StorySegment/properties/kind/enum",keyword:"enum",params:{allowedValues: schema37.properties.kind.enum},message:"must be equal to one of the allowed values"}];
return false;
}
var valid10 = _errs63 === errors;
}
else {
var valid10 = true;
}
if(valid10){
if(data23.speaker_id !== undefined){
const _errs65 = errors;
if(typeof data23.speaker_id !== "string"){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1+"/speaker_id",schemaPath:"#/$defs/StorySegment/properties/speaker_id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid10 = _errs65 === errors;
}
else {
var valid10 = true;
}
if(valid10){
if(data23.speaker_name !== undefined){
const _errs67 = errors;
if(typeof data23.speaker_name !== "string"){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1+"/speaker_name",schemaPath:"#/$defs/StorySegment/properties/speaker_name/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid10 = _errs67 === errors;
}
else {
var valid10 = true;
}
if(valid10){
if(data23.text !== undefined){
const _errs69 = errors;
if(typeof data23.text !== "string"){
validate21.errors = [{instancePath:instancePath+"/segments/" + i1+"/text",schemaPath:"#/$defs/StorySegment/properties/text/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid10 = _errs69 === errors;
}
else {
var valid10 = true;
}
}
}
}
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/segments/" + i1,schemaPath:"#/$defs/StorySegment/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
var valid8 = _errs59 === errors;
if(!valid8){
break;
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/segments",schemaPath:"#/properties/segments/type",keyword:"type",params:{type: "array"},message:"must be array"}];
return false;
}
}
var valid0 = _errs57 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.state_version !== undefined){
let data28 = data.state_version;
const _errs71 = errors;
if(!(((typeof data28 == "number") && (!(data28 % 1) && !isNaN(data28))) && (isFinite(data28)))){
validate21.errors = [{instancePath:instancePath+"/state_version",schemaPath:"#/properties/state_version/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid0 = _errs71 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.status_fields !== undefined){
let data29 = data.status_fields;
const _errs73 = errors;
if(errors === _errs73){
if(Array.isArray(data29)){
var valid11 = true;
const len2 = data29.length;
for(let i2=0; i2<len2; i2++){
let data30 = data29[i2];
const _errs75 = errors;
const _errs76 = errors;
if(errors === _errs76){
if(data30 && typeof data30 == "object" && !Array.isArray(data30)){
let missing4;
if((((data30.id === undefined) && (missing4 = "id")) || ((data30.label === undefined) && (missing4 = "label"))) || ((data30.value === undefined) && (missing4 = "value"))){
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2,schemaPath:"#/$defs/StatusField/required",keyword:"required",params:{missingProperty: missing4},message:"must have required property '"+missing4+"'"}];
return false;
}
else {
const _errs78 = errors;
for(const key4 in data30){
if(!(((((key4 === "id") || (key4 === "label")) || (key4 === "max")) || (key4 === "min")) || (key4 === "value"))){
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2,schemaPath:"#/$defs/StatusField/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key4},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs78 === errors){
if(data30.id !== undefined){
const _errs79 = errors;
if(typeof data30.id !== "string"){
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2+"/id",schemaPath:"#/$defs/StatusField/properties/id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid13 = _errs79 === errors;
}
else {
var valid13 = true;
}
if(valid13){
if(data30.label !== undefined){
const _errs81 = errors;
if(typeof data30.label !== "string"){
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2+"/label",schemaPath:"#/$defs/StatusField/properties/label/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid13 = _errs81 === errors;
}
else {
var valid13 = true;
}
if(valid13){
if(data30.max !== undefined){
let data33 = data30.max;
const _errs83 = errors;
if(!(((typeof data33 == "number") && (!(data33 % 1) && !isNaN(data33))) && (isFinite(data33)))){
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2+"/max",schemaPath:"#/$defs/StatusField/properties/max/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid13 = _errs83 === errors;
}
else {
var valid13 = true;
}
if(valid13){
if(data30.min !== undefined){
let data34 = data30.min;
const _errs85 = errors;
if(!(((typeof data34 == "number") && (!(data34 % 1) && !isNaN(data34))) && (isFinite(data34)))){
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2+"/min",schemaPath:"#/$defs/StatusField/properties/min/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid13 = _errs85 === errors;
}
else {
var valid13 = true;
}
if(valid13){
if(data30.value !== undefined){
let data35 = data30.value;
const _errs87 = errors;
const _errs88 = errors;
let valid14 = false;
const _errs89 = errors;
if(typeof data35 !== "string"){
const err5 = {instancePath:instancePath+"/status_fields/" + i2+"/value",schemaPath:"#/$defs/StatusField/properties/value/anyOf/0/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
var _valid2 = _errs89 === errors;
valid14 = valid14 || _valid2;
const _errs91 = errors;
if(!(((typeof data35 == "number") && (!(data35 % 1) && !isNaN(data35))) && (isFinite(data35)))){
const err6 = {instancePath:instancePath+"/status_fields/" + i2+"/value",schemaPath:"#/$defs/StatusField/properties/value/anyOf/1/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
var _valid2 = _errs91 === errors;
valid14 = valid14 || _valid2;
const _errs93 = errors;
if(typeof data35 !== "boolean"){
const err7 = {instancePath:instancePath+"/status_fields/" + i2+"/value",schemaPath:"#/$defs/StatusField/properties/value/anyOf/2/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
var _valid2 = _errs93 === errors;
valid14 = valid14 || _valid2;
if(!valid14){
const err8 = {instancePath:instancePath+"/status_fields/" + i2+"/value",schemaPath:"#/$defs/StatusField/properties/value/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
validate21.errors = vErrors;
return false;
}
else {
errors = _errs88;
if(vErrors !== null){
if(_errs88){
vErrors.length = _errs88;
}
else {
vErrors = null;
}
}
}
var valid13 = _errs87 === errors;
}
else {
var valid13 = true;
}
}
}
}
}
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/status_fields/" + i2,schemaPath:"#/$defs/StatusField/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
var valid11 = _errs75 === errors;
if(!valid11){
break;
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/status_fields",schemaPath:"#/properties/status_fields/type",keyword:"type",params:{type: "array"},message:"must be array"}];
return false;
}
}
var valid0 = _errs73 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.suggestions !== undefined){
let data36 = data.suggestions;
const _errs95 = errors;
if(errors === _errs95){
if(Array.isArray(data36)){
var valid15 = true;
const len3 = data36.length;
for(let i3=0; i3<len3; i3++){
const _errs97 = errors;
if(typeof data36[i3] !== "string"){
validate21.errors = [{instancePath:instancePath+"/suggestions/" + i3,schemaPath:"#/properties/suggestions/items/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid15 = _errs97 === errors;
if(!valid15){
break;
}
}
}
else {
validate21.errors = [{instancePath:instancePath+"/suggestions",schemaPath:"#/properties/suggestions/type",keyword:"type",params:{type: "array"},message:"must be array"}];
return false;
}
}
var valid0 = _errs95 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.tick !== undefined){
let data38 = data.tick;
const _errs99 = errors;
if(!(((typeof data38 == "number") && (!(data38 % 1) && !isNaN(data38))) && (isFinite(data38)))){
validate21.errors = [{instancePath:instancePath+"/tick",schemaPath:"#/properties/tick/type",keyword:"type",params:{type: "integer"},message:"must be integer"}];
return false;
}
var valid0 = _errs99 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.time_of_day !== undefined){
let data39 = data.time_of_day;
const _errs101 = errors;
const _errs102 = errors;
let valid16 = false;
const _errs103 = errors;
if(typeof data39 !== "string"){
const err9 = {instancePath:instancePath+"/time_of_day",schemaPath:"#/properties/time_of_day/anyOf/0/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
var _valid3 = _errs103 === errors;
valid16 = valid16 || _valid3;
const _errs105 = errors;
if(data39 !== null){
const err10 = {instancePath:instancePath+"/time_of_day",schemaPath:"#/properties/time_of_day/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
var _valid3 = _errs105 === errors;
valid16 = valid16 || _valid3;
if(!valid16){
const err11 = {instancePath:instancePath+"/time_of_day",schemaPath:"#/properties/time_of_day/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
validate21.errors = vErrors;
return false;
}
else {
errors = _errs102;
if(vErrors !== null){
if(_errs102){
vErrors.length = _errs102;
}
else {
vErrors = null;
}
}
}
var valid0 = _errs101 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.turn_id !== undefined){
let data40 = data.turn_id;
const _errs107 = errors;
const _errs108 = errors;
let valid17 = false;
const _errs109 = errors;
if(typeof data40 !== "string"){
const err12 = {instancePath:instancePath+"/turn_id",schemaPath:"#/properties/turn_id/anyOf/0/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
var _valid4 = _errs109 === errors;
valid17 = valid17 || _valid4;
const _errs111 = errors;
if(data40 !== null){
const err13 = {instancePath:instancePath+"/turn_id",schemaPath:"#/properties/turn_id/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
var _valid4 = _errs111 === errors;
valid17 = valid17 || _valid4;
if(!valid17){
const err14 = {instancePath:instancePath+"/turn_id",schemaPath:"#/properties/turn_id/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
validate21.errors = vErrors;
return false;
}
else {
errors = _errs108;
if(vErrors !== null){
if(_errs108){
vErrors.length = _errs108;
}
else {
vErrors = null;
}
}
}
var valid0 = _errs107 === errors;
}
else {
var valid0 = true;
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
}
else {
validate21.errors = [{instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
validate21.errors = vErrors;
return errors === 0;
}
validate21.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};

const schema39 = {"additionalProperties":false,"properties":{"input":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Input"},"request_id":{"title":"Request Id","type":"string"},"response":{"$ref":"#/$defs/View"}},"required":["request_id","input","response"],"title":"HistoryTurn","type":"object"};

function validate25(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate25.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(errors === 0){
if(data && typeof data == "object" && !Array.isArray(data)){
let missing0;
if((((data.request_id === undefined) && (missing0 = "request_id")) || ((data.input === undefined) && (missing0 = "input"))) || ((data.response === undefined) && (missing0 = "response"))){
validate25.errors = [{instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: missing0},message:"must have required property '"+missing0+"'"}];
return false;
}
else {
const _errs1 = errors;
for(const key0 in data){
if(!(((key0 === "input") || (key0 === "request_id")) || (key0 === "response"))){
validate25.errors = [{instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs1 === errors){
if(data.input !== undefined){
let data0 = data.input;
const _errs2 = errors;
const _errs3 = errors;
let valid1 = false;
const _errs4 = errors;
if(typeof data0 !== "string"){
const err0 = {instancePath:instancePath+"/input",schemaPath:"#/properties/input/anyOf/0/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
var _valid0 = _errs4 === errors;
valid1 = valid1 || _valid0;
const _errs6 = errors;
if(data0 !== null){
const err1 = {instancePath:instancePath+"/input",schemaPath:"#/properties/input/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
var _valid0 = _errs6 === errors;
valid1 = valid1 || _valid0;
if(!valid1){
const err2 = {instancePath:instancePath+"/input",schemaPath:"#/properties/input/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
validate25.errors = vErrors;
return false;
}
else {
errors = _errs3;
if(vErrors !== null){
if(_errs3){
vErrors.length = _errs3;
}
else {
vErrors = null;
}
}
}
var valid0 = _errs2 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.request_id !== undefined){
const _errs8 = errors;
if(typeof data.request_id !== "string"){
validate25.errors = [{instancePath:instancePath+"/request_id",schemaPath:"#/properties/request_id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs8 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.response !== undefined){
const _errs10 = errors;
if(!(validate21(data.response, {instancePath:instancePath+"/response",parentData:data,parentDataProperty:"response",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate21.errors : vErrors.concat(validate21.errors);
errors = vErrors.length;
}
var valid0 = _errs10 === errors;
}
else {
var valid0 = true;
}
}
}
}
}
}
else {
validate25.errors = [{instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
validate25.errors = vErrors;
return errors === 0;
}
validate25.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};


function validate20(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
let vErrors = null;
let errors = 0;
const evaluated0 = validate20.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(errors === 0){
if(data && typeof data == "object" && !Array.isArray(data)){
let missing0;
if((((data.game_id === undefined) && (missing0 = "game_id")) || ((data.intro === undefined) && (missing0 = "intro"))) || ((data.turns === undefined) && (missing0 = "turns"))){
validate20.errors = [{instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: missing0},message:"must have required property '"+missing0+"'"}];
return false;
}
else {
const _errs1 = errors;
for(const key0 in data){
if(!(((key0 === "game_id") || (key0 === "intro")) || (key0 === "turns"))){
validate20.errors = [{instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs1 === errors){
if(data.game_id !== undefined){
const _errs2 = errors;
if(typeof data.game_id !== "string"){
validate20.errors = [{instancePath:instancePath+"/game_id",schemaPath:"#/properties/game_id/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs2 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.intro !== undefined){
const _errs4 = errors;
if(!(validate21(data.intro, {instancePath:instancePath+"/intro",parentData:data,parentDataProperty:"intro",rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate21.errors : vErrors.concat(validate21.errors);
errors = vErrors.length;
}
var valid0 = _errs4 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.turns !== undefined){
let data2 = data.turns;
const _errs5 = errors;
if(errors === _errs5){
if(Array.isArray(data2)){
var valid1 = true;
const len0 = data2.length;
for(let i0=0; i0<len0; i0++){
const _errs7 = errors;
if(!(validate25(data2[i0], {instancePath:instancePath+"/turns/" + i0,parentData:data2,parentDataProperty:i0,rootData,dynamicAnchors}))){
vErrors = vErrors === null ? validate25.errors : vErrors.concat(validate25.errors);
errors = vErrors.length;
}
var valid1 = _errs7 === errors;
if(!valid1){
break;
}
}
}
else {
validate20.errors = [{instancePath:instancePath+"/turns",schemaPath:"#/properties/turns/type",keyword:"type",params:{type: "array"},message:"must be array"}];
return false;
}
}
var valid0 = _errs5 === errors;
}
else {
var valid0 = true;
}
}
}
}
}
}
else {
validate20.errors = [{instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
validate20.errors = vErrors;
return errors === 0;
}
validate20.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};
