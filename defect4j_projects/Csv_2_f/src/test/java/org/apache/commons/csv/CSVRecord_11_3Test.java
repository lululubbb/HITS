package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;

import java.lang.reflect.Field;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_11_3Test {

    private CSVRecord csvRecord;

    @BeforeEach
    public void setUp() throws Exception {
        String[] values = new String[] { "a", "b", "c" };
        Map<String, Integer> mapping = mock(Map.class);
        String comment = "comment";
        long recordNumber = 1L;

        csvRecord = new CSVRecord(values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    public void testSize() throws Exception {
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);

        // Remove final modifier on 'values' field
        Field modifiersField = Field.class.getDeclaredField("modifiers");
        modifiersField.setAccessible(true);
        modifiersField.setInt(valuesField, valuesField.getModifiers() & ~java.lang.reflect.Modifier.FINAL);

        valuesField.set(csvRecord, new String[] { "x", "y", "z" });
        assertEquals(3, csvRecord.size());

        valuesField.set(csvRecord, new String[0]);
        assertEquals(0, csvRecord.size());

        valuesField.set(csvRecord, new String[] { "onlyOne" });
        assertEquals(1, csvRecord.size());
    }
}