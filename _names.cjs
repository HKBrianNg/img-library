const fs = require('fs');
const d = JSON.parse(fs.readFileSync('openEDU/EnglishWord/Kindergarten.json', 'utf8'));
const withUrl = d.filter((x) => x.url && x.url.trim());
const without = d.filter((x) => !(x.url && x.url.trim()));
console.log('  数据里显式带 url 的（' + withUrl.length + ' 条）:');
withUrl.slice(0, 4).forEach((x) => console.log('    en = ' + JSON.stringify(x.en) + '  url = ' + JSON.stringify(x.url)));
console.log('  没带 url 的（' + without.length + ' 条）—— 文件名由英文名推出来:');
const toFile = (en) => en.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '') + '.jpg';
without.slice(0, 4).forEach((x) => console.log('    en = ' + JSON.stringify(x.en) + '  ->  ' + toFile(x.en)));
