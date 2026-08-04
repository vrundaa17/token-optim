console.log("hello world of optimeeee")


document.addEventListener("input", function(event) {
    const el=event.target
    if (!el.isContentEditable) {
        return;
    }
    const text = el.innerText;
    fetch("http://localhost:8001/count?text=" + encodeURIComponent(text))
    .then(response => response.json())
    .then(data => {console.log("Tokens : ", data.tokens);});
});