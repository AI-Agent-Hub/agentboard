document.querySelectorAll('.toggle-btn').forEach(button => {
    button.addEventListener('click', () => {
        const question = button.nextElementSibling;
        const isVisible = question.querySelector('p').style.display === 'block';

        // Toggle display of the answer
        question.querySelector('p').style.display = isVisible ? 'none' : 'block';

        // Change button symbol
        button.textContent = isVisible ? '+' : '−';
    });
});
