// Generated from api/contracts.py.
"use strict";
export const validate = validate20;
export default validate20;
const schema31 = {"additionalProperties":false,"properties":{"code":{"title":"Code","type":"string"},"commit_state":{"enum":["not_started","committed","unknown"],"title":"Commit State","type":"string"},"detail":{"default":null,"title":"Detail","type":"string"},"message":{"title":"Message","type":"string"},"request_id":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Request Id"},"retryable":{"title":"Retryable","type":"boolean"}},"required":["code","message","retryable","commit_state","request_id"],"title":"TurnFailure","type":"object"};

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
if((((((data.code === undefined) && (missing0 = "code")) || ((data.message === undefined) && (missing0 = "message"))) || ((data.retryable === undefined) && (missing0 = "retryable"))) || ((data.commit_state === undefined) && (missing0 = "commit_state"))) || ((data.request_id === undefined) && (missing0 = "request_id"))){
validate20.errors = [{instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: missing0},message:"must have required property '"+missing0+"'"}];
return false;
}
else {
const _errs1 = errors;
for(const key0 in data){
if(!((((((key0 === "code") || (key0 === "commit_state")) || (key0 === "detail")) || (key0 === "message")) || (key0 === "request_id")) || (key0 === "retryable"))){
validate20.errors = [{instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"}];
return false;
break;
}
}
if(_errs1 === errors){
if(data.code !== undefined){
const _errs2 = errors;
if(typeof data.code !== "string"){
validate20.errors = [{instancePath:instancePath+"/code",schemaPath:"#/properties/code/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs2 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.commit_state !== undefined){
let data1 = data.commit_state;
const _errs4 = errors;
if(typeof data1 !== "string"){
validate20.errors = [{instancePath:instancePath+"/commit_state",schemaPath:"#/properties/commit_state/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
if(!(((data1 === "not_started") || (data1 === "committed")) || (data1 === "unknown"))){
validate20.errors = [{instancePath:instancePath+"/commit_state",schemaPath:"#/properties/commit_state/enum",keyword:"enum",params:{allowedValues: schema31.properties.commit_state.enum},message:"must be equal to one of the allowed values"}];
return false;
}
var valid0 = _errs4 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.detail !== undefined){
const _errs6 = errors;
if(typeof data.detail !== "string"){
validate20.errors = [{instancePath:instancePath+"/detail",schemaPath:"#/properties/detail/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs6 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.message !== undefined){
const _errs8 = errors;
if(typeof data.message !== "string"){
validate20.errors = [{instancePath:instancePath+"/message",schemaPath:"#/properties/message/type",keyword:"type",params:{type: "string"},message:"must be string"}];
return false;
}
var valid0 = _errs8 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.request_id !== undefined){
let data4 = data.request_id;
const _errs10 = errors;
const _errs11 = errors;
let valid1 = false;
const _errs12 = errors;
if(typeof data4 !== "string"){
const err0 = {instancePath:instancePath+"/request_id",schemaPath:"#/properties/request_id/anyOf/0/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
var _valid0 = _errs12 === errors;
valid1 = valid1 || _valid0;
const _errs14 = errors;
if(data4 !== null){
const err1 = {instancePath:instancePath+"/request_id",schemaPath:"#/properties/request_id/anyOf/1/type",keyword:"type",params:{type: "null"},message:"must be null"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
var _valid0 = _errs14 === errors;
valid1 = valid1 || _valid0;
if(!valid1){
const err2 = {instancePath:instancePath+"/request_id",schemaPath:"#/properties/request_id/anyOf",keyword:"anyOf",params:{},message:"must match a schema in anyOf"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
validate20.errors = vErrors;
return false;
}
else {
errors = _errs11;
if(vErrors !== null){
if(_errs11){
vErrors.length = _errs11;
}
else {
vErrors = null;
}
}
}
var valid0 = _errs10 === errors;
}
else {
var valid0 = true;
}
if(valid0){
if(data.retryable !== undefined){
const _errs16 = errors;
if(typeof data.retryable !== "boolean"){
validate20.errors = [{instancePath:instancePath+"/retryable",schemaPath:"#/properties/retryable/type",keyword:"type",params:{type: "boolean"},message:"must be boolean"}];
return false;
}
var valid0 = _errs16 === errors;
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
else {
validate20.errors = [{instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"}];
return false;
}
}
validate20.errors = vErrors;
return errors === 0;
}
validate20.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};
