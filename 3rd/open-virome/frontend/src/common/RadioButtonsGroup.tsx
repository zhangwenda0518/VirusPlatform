import * as React from 'react';

import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';

const RadioButtonsGroup = ({ items, selected, onChange, props = {} }) => {
    return (
        <FormControl sx={{ minWidth: 200 }}>
            <RadioGroup
                aria-labelledby='demo-radio-buttons-group-label'
                defaultValue={items[0]}
                name='radio-buttons-group'
                value={selected}
                onChange={onChange}
                {...props}
            >
                {Object.keys(items).map((key, index) => {
                    return <FormControlLabel key={index} value={key} control={<Radio />} label={items[key]} />;
                })}
            </RadioGroup>
        </FormControl>
    );
};

export default RadioButtonsGroup;
