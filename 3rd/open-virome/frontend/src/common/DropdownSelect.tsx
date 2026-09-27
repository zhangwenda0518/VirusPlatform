import * as React from 'react';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';

const DropDownSelect = ({ styles = {}, options = [], activeOption = '', setActiveOption = () => {}, label = '' }) => {
    const menuStyles = {
        PaperProps: {
            style: {
                maxHeight: 200,
                width: 100,
            },
        },
    };

    return (
        <FormControl sx={{ m: 1, minWidth: 120 }} size='small'>
            <InputLabel id='demo-select-small-label'>{label}</InputLabel>
            <Select
                labelId='demo-select-small-label'
                id='demo-select-small'
                value={activeOption}
                label={label}
                onChange={setActiveOption}
                MenuProps={menuStyles}
                sx={styles}
            >
                {options.map((option, index) => {
                    return (
                        <MenuItem key={index} value={option}>
                            {option}
                        </MenuItem>
                    );
                })}
            </Select>
        </FormControl>
    );
};

export default DropDownSelect;
