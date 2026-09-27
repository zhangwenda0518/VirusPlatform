import React from 'react';
import Paper from '@mui/material/Paper';
import InputBase from '@mui/material/InputBase';
import IconButton from '@mui/material/IconButton';
import SearchIcon from '@mui/icons-material/Search';

const SearchBar = ({ query, setQuery, placeholder = 'Search' }) => {
    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            return;
        }
    };

    const handleOnChange = (e) => {
        setQuery(e.target.value);
    };

    const handleIconClick = () => {
        return;
    };

    return (
        <Paper
            sx={{
                display: 'flex',
                alignItems: 'center',
                height: 40,
                flex: 1,
            }}
        >
            <InputBase
                autoFocus
                placeholder={placeholder}
                onKeyDown={handleKeyDown}
                onChange={handleOnChange}
                value={query}
                sx={{
                    'marginLeft': 2,
                    'flex': 1,
                    '&::placeholder': {
                        paddingLeft: 10,
                    },
                }}
            />
            <IconButton aria-label='search' onClick={handleIconClick}>
                <SearchIcon fontSize='medium' />
            </IconButton>
        </Paper>
    );
};

export default SearchBar;
