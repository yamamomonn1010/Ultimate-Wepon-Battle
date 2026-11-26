const lines = [...document.querySelectorAll("#commentary li")];
const playback = document.querySelector("#playback");
const result = document.querySelector("#result");
let nextLine = 1;

for (const line of lines.slice(nextLine)) {
  line.hidden = true;
}
result.hidden = true;
playback.hidden = false;

function showResult() {
  for (const line of lines.slice(nextLine)) {
    line.hidden = false;
  }
  playback.hidden = true;
  result.hidden = false;
  document.querySelector("#verdict").focus();
}

document.querySelector("#advance").addEventListener("click", () => {
  if (nextLine === lines.length) {
    showResult();
    return;
  }
  lines[nextLine].hidden = false;
  nextLine += 1;
});
document.querySelector("#skip").addEventListener("click", showResult);
